"""
app/reference_agent.py — Controller Reference Database agent.

Queries the local reference-document database under data/controllers/ (one folder
per controller + shared _common/ theory; see manifest.json). It:

  1. reads manifest.json,
  2. extracts text from the PDF references (PyMuPDF), one chunk per page,
  3. retrieves the most relevant passages with a pure-Python BM25 ranker
     (no extra dependencies — no embeddings service required),
  4. optionally synthesises a grounded, cited answer with Claude when an
     ANTHROPIC_API_KEY is configured (gracefully degrades to retrieval-only).

The page-level BM25 index is cached to data/controllers/.index.json and rebuilt
only when the underlying files change (mtime/size signature).

Public API:
    agent = get_agent()
    agent.sources(controller=None)                      -> manifest + index status
    agent.query(question, controller=None, k=6,
                synthesize=False)                        -> {answer, passages, ...}
"""
from __future__ import annotations

import json, math, re, logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("pfc_ai.reference_agent")

DB_DIR    = Path(__file__).resolve().parent.parent / "data" / "controllers"
MANIFEST  = DB_DIR / "manifest.json"
INDEX     = DB_DIR / ".index.json"

# BM25 parameters
_K1, _B = 1.5, 0.75

_STOP = set((
    "the a an of to in for and or is are be by with on at as from this that it its into "
    "use used using can may will which when where than then so such other over under per "
    "via if not no than these those each both all any more most some out about also one two"
).split())
_TOK = re.compile(r"[a-z0-9]+")

# File types we can full-text index. PDFs via PyMuPDF; HTML / MHTML (incl. the
# project's HTML-based Word ".doc" exports) via tag stripping. Binary OLE .doc
# and other formats are listed in the manifest but not searched.
_INDEXABLE = (".pdf", ".doc", ".html", ".htm", ".mht", ".mhtml")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOK.findall(text.lower()) if len(t) >= 2 and t not in _STOP]


def _html_to_text(raw: bytes) -> str:
    """Strip an HTML or MHTML (multipart/related) byte payload to plain text."""
    import email
    html = None
    if raw[:64].lstrip().startswith(b"MIME-Version") or b"multipart/related" in raw[:800]:
        try:
            msg = email.message_from_bytes(raw)
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True) or b""
                    html = payload.decode(part.get_content_charset() or "utf-8", "ignore")
                    break
        except Exception:
            html = None
    if html is None:
        html = raw.decode("utf-8", "ignore")
    html = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", html)   # drop JS/CSS
    html = re.sub(r"(?s)<[^>]+>", " ", html)                             # drop tags
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">"))
    html = re.sub(r"&#?\w+;", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _extract_document(path: Path) -> list[tuple[str, str]]:
    """Return [(loc, text), ...] for one file. loc is 'p.N' (PDF pages) or
    '§N' (HTML windows). Returns [] for formats we cannot read."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        out = [(f"p.{i + 1}", doc[i].get_text("text")) for i in range(doc.page_count)]
        doc.close()
        return out
    # HTML / MHTML / HTML-based .doc
    raw = path.read_bytes()
    if raw[:4] == b"\xd0\xcf\x11\xe0":      # OLE2 binary Word — not extractable here
        log.info("skip %s — binary OLE Word (not indexable)", path.name)
        return []
    text = _html_to_text(raw)
    if len(text) < 20:
        return []
    out, i, n, seg = [], 0, len(text), 1                # ~1800-char windows on word breaks
    while i < n:
        j = min(n, i + 1800)
        if j < n:
            sp = text.rfind(" ", i + 1200, j)
            if sp > i:
                j = sp
        out.append((f"§{seg}", text[i:j]))
        i, seg = j, seg + 1
    return out


# ── manifest → list of indexable documents ─────────────────────────────────────
def _iter_manifest_docs(manifest: dict):
    """Yield (relpath, meta) for every document declared in the manifest.

    meta = {controller, collection, file, doc_no, title, type}
    controller is None for shared (_common) collections; collection is None for
    controller-folder documents.
    """
    for cid, c in (manifest.get("controllers") or {}).items():
        folder = c.get("folder", cid)
        for d in c.get("documents", []):
            yield f"{folder}/{d['file']}", {
                "controller": cid, "collection": None,
                "file": d["file"], "doc_no": d.get("doc_no"),
                "title": d.get("title"), "type": d.get("type"),
            }
    for coll_id, coll in (manifest.get("common") or {}).items():
        folder = coll.get("folder", f"_common/{coll_id}")
        for d in coll.get("documents", []):
            yield f"{folder}/{d['file']}", {
                "controller": None, "collection": coll_id,
                "file": d["file"], "doc_no": d.get("doc_no"),
                "title": d.get("title"), "type": d.get("type"),
            }


def _file_signature(relpaths: list[str]) -> dict:
    sig = {}
    for rel in relpaths:
        p = DB_DIR / rel
        if p.exists():
            st = p.stat()
            sig[rel] = [int(st.st_mtime), st.st_size]
    return sig


class ControllerReferenceAgent:
    def __init__(self) -> None:
        self._idx: Optional[dict] = None

    # ── manifest ───────────────────────────────────────────────────────────────
    def _manifest(self) -> dict:
        if not MANIFEST.exists():
            raise FileNotFoundError(f"manifest not found: {MANIFEST}")
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    # ── index (lazy, cached, freshness-checked) ─────────────────────────────────
    def _index(self) -> dict:
        if self._idx is not None:
            return self._idx
        manifest = self._manifest()
        idx_rels = [rel for rel, _ in _iter_manifest_docs(manifest)
                    if rel.lower().endswith(_INDEXABLE)]
        sig = _file_signature(idx_rels)

        if INDEX.exists():
            try:
                cached = json.loads(INDEX.read_text(encoding="utf-8"))
                if cached.get("signature") == sig:
                    self._idx = cached
                    return cached
            except Exception:
                log.warning("reference index cache unreadable — rebuilding")

        self._idx = self._build_index(manifest, sig)
        return self._idx

    def _build_index(self, manifest: dict, sig: dict) -> dict:
        meta_by_rel = {rel: m for rel, m in _iter_manifest_docs(manifest)}
        chunks: list[dict] = []
        df: dict[str, int] = {}
        n_files = 0

        for rel in sig:                       # only files that exist
            meta = meta_by_rel.get(rel, {})
            try:
                units = _extract_document(DB_DIR / rel)
            except Exception as ex:
                log.warning("skip %s — extraction failed (%s)", rel, ex)
                continue
            if not units:
                continue
            n_files += 1
            for loc, text in units:
                text = (text or "").strip()
                if len(text) < 20:
                    continue
                toks = _tokenize(text)
                if not toks:
                    continue
                tf: dict[str, int] = {}
                for t in toks:
                    tf[t] = tf.get(t, 0) + 1
                for t in tf:
                    df[t] = df.get(t, 0) + 1
                chunks.append({
                    "id": f"{rel}#{loc}",
                    "rel": rel,
                    "controller": meta.get("controller"),
                    "collection": meta.get("collection"),
                    "file": meta.get("file") or Path(rel).name,
                    "doc_no": meta.get("doc_no"),
                    "title": meta.get("title"),
                    "loc": loc,
                    "text": text,
                    "tf": tf,
                    "dl": len(toks),
                })

        N = len(chunks)
        avgdl = (sum(c["dl"] for c in chunks) / N) if N else 1.0
        index = {"signature": sig, "chunks": chunks, "df": df, "N": N, "avgdl": avgdl,
                 "controllers": list((manifest.get("controllers") or {}).keys())}
        try:
            INDEX.write_text(json.dumps(index), encoding="utf-8")
        except Exception as ex:
            log.warning("could not write index cache: %s", ex)
        log.info("reference index built: %d chunks from %d files", N, n_files)
        return index

    # ── scoping ──────────────────────────────────────────────────────────────────
    def _scope(self, manifest: dict, controller: Optional[str]):
        """Return a predicate selecting chunks visible for `controller`."""
        if not controller:
            return lambda c: True
        cmeta = (manifest.get("controllers") or {}).get(controller)
        commons = set(cmeta.get("common_collections", [])) if cmeta else set()
        return lambda c: (c["controller"] == controller) or (c["collection"] in commons)

    # ── BM25 ─────────────────────────────────────────────────────────────────────
    def _bm25(self, qterms: list[str], chunk: dict, df: dict, N: int, avgdl: float) -> float:
        score, dl = 0.0, chunk["dl"]
        tf = chunk["tf"]
        for t in qterms:
            f = tf.get(t, 0)
            if not f:
                continue
            n_t = df.get(t, 0)
            idf = math.log(1 + (N - n_t + 0.5) / (n_t + 0.5))
            score += idf * (f * (_K1 + 1)) / (f + _K1 * (1 - _B + _B * dl / avgdl))
        return score

    @staticmethod
    def _snippet(text: str, qterms: list[str], width: int = 320) -> str:
        low = text.lower()
        pos = min([low.find(t) for t in qterms if low.find(t) >= 0] or [0])
        start = max(0, pos - width // 3)
        chunk = re.sub(r"\s+", " ", text[start:start + width]).strip()
        return ("…" if start > 0 else "") + chunk + "…"

    # ── public: sources ──────────────────────────────────────────────────────────
    def sources(self, controller: Optional[str] = None) -> dict:
        manifest = self._manifest()
        out = {"description": manifest.get("description"), "controllers": {}, "common": {}}
        for cid, c in (manifest.get("controllers") or {}).items():
            if controller and cid != controller:
                continue
            out["controllers"][cid] = {
                "name": c.get("name"), "summary": c.get("summary"),
                "common_collections": c.get("common_collections", []),
                "documents": [{k: d.get(k) for k in ("file", "doc_no", "type", "title", "pages")}
                              for d in c.get("documents", [])],
                "missing": c.get("missing", []),
            }
        for coll_id, coll in (manifest.get("common") or {}).items():
            out["common"][coll_id] = {
                "summary": coll.get("summary"),
                "documents": [{k: d.get(k) for k in ("file", "doc_no", "type", "title", "pages")}
                              for d in coll.get("documents", [])],
            }
        return out

    # ── public: query ────────────────────────────────────────────────────────────
    def query(self, question: str, controller: Optional[str] = None,
              k: int = 6, synthesize: bool = False) -> dict:
        question = (question or "").strip()
        if not question:
            return {"error": "empty question", "passages": []}
        manifest = self._manifest()
        idx = self._index()
        in_scope = self._scope(manifest, controller)
        qterms = _tokenize(question)
        if not qterms:
            return {"error": "no searchable terms in question", "passages": []}

        df, N, avgdl = idx["df"], idx["N"], idx["avgdl"]
        scored = []
        for c in idx["chunks"]:
            if not in_scope(c):
                continue
            s = self._bm25(qterms, c, df, N, avgdl)
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: max(1, k)]

        passages = [{
            "rank": i + 1,
            "score": round(s, 3),
            "controller": c["controller"],
            "collection": c["collection"],
            "file": c["file"],
            "doc_no": c["doc_no"],
            "title": c["title"],
            "loc": c["loc"],
            "citation": f"{c['doc_no'] or c['file']} {c['loc']}",
            "snippet": self._snippet(c["text"], qterms),
        } for i, (s, c) in enumerate(top)]

        result = {
            "question": question,
            "controller": controller,
            "scope_pages": sum(1 for c in idx["chunks"] if in_scope(c)),
            "passages": passages,
            "answer": None,
            "used_llm": False,
        }
        if synthesize and passages:
            answer, used_llm = self._synthesize(question, top)
            result["answer"], result["used_llm"] = answer, used_llm
        return result

    # ── optional LLM synthesis (graceful degrade) ─────────────────────────────────
    def _synthesize(self, question: str, top: list) -> tuple[Optional[str], bool]:
        try:
            import anthropic
        except ImportError:
            return ("LLM synthesis unavailable — the 'anthropic' package is not installed; "
                    "returning retrieved passages only.", False)
        try:
            client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
            ctx = "\n\n".join(
                f"[{c['doc_no'] or c['file']} {c['loc']}] ({c['title']})\n{c['text'][:1600]}"
                for _s, c in top
            )
            system = (
                "You are a reference assistant for analog PFC controller and control-loop design. "
                "Answer the question using ONLY the provided excerpts from the local reference "
                "database. Cite every claim inline using the bracket tag shown for each excerpt, "
                "e.g. [FAN9672-D p.12]. Be concise and technical. If the excerpts do not contain "
                "the answer, say so explicitly rather than guessing."
            )
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                system=system,
                messages=[{"role": "user",
                           "content": f"Question: {question}\n\nExcerpts:\n{ctx}"}],
            )
            return resp.content[0].text, True
        except Exception as ex:
            log.warning("LLM synthesis failed: %s", ex)
            return (f"LLM synthesis unavailable ({ex}); returning retrieved passages only.", False)


_AGENT: Optional[ControllerReferenceAgent] = None


def get_agent() -> ControllerReferenceAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = ControllerReferenceAgent()
    return _AGENT


# ── CLI: build index / run a sample query ──────────────────────────────────────
if __name__ == "__main__":
    import sys
    a = get_agent()
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        ctrl = "fan9672"
        res = a.query(q, controller=ctrl, k=5)
        print(f"Q: {q}  (controller={ctrl}, scope={res['scope_pages']} pages)\n")
        for p in res["passages"]:
            print(f"  #{p['rank']} [{p['citation']}] score={p['score']}  {p['title']}")
            print(f"      {p['snippet'][:200]}\n")
    else:
        idx = a._index()
        print(f"Indexed {idx['N']} pages across {len(idx['signature'])} PDFs.")
        print("Sources:", json.dumps(a.sources(), indent=2)[:800])
