"""Which datasheets would close PENDING A1, A2 and A3, in the order worth reading them.

    cd backend && PYTHONUTF8=1 venv/Scripts/python.exe surge_datasheet_worklist.py

A2 (MOV `Vc @ In`, missing on 1140/1140) and A3 (GDT impulse sparkover + follow current, missing on
172/172) read as 1312 separate problems. They are not. Every part carries a datasheet URL, and the
parts collapse onto far fewer documents:

    MOV   1140 parts  ->  84 distinct datasheets  ->  19 of them cover 80% of the parts
    GDT    172 parts  ->  87 distinct datasheets  ->  53 of them cover 80%

So the MOV half is roughly twenty documents for the bulk of the catalogue, and the GDT half has
little leverage but is small in absolute terms.

A SCRIPT, NOT A CHECKED-IN LIST. This repo has been bitten more than once by a written-down list of
sites going stale while a count stayed honest (C2 and C3 each grew an entry nobody re-counted). The
worklist is derived from the workbooks every time it is run, so it cannot drift from them; the CSV
it writes is an output, not a source.

WHAT IT CANNOT TELL YOU: whether a URL still resolves, or whether the datasheet actually publishes
the field. Both need the document. This ranks the reading order and nothing more.
"""
from __future__ import annotations

import collections
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.mode_b.inputprotection import database as DB   # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "specs", "Improvements")


def _clean(url) -> str:
    u = str(url or "").strip()
    return "" if u in ("-", "—", "N/A", "None") else u


def _worklist(rows: list[dict], missing_fields: list[str]) -> tuple[list[dict], dict]:
    """One entry per distinct datasheet, with the parts it would unblock."""
    by_url: dict[str, list[dict]] = collections.defaultdict(list)
    unlinked: list[dict] = []
    for r in rows:
        u = _clean(r.get("datasheet_url")) or _clean(r.get("url"))
        (by_url[u] if u else unlinked).append(r)

    work = []
    for url, parts in by_url.items():
        # A part is only worth listing if it is actually still missing the field.
        needs = [p for p in parts if any(p.get(f) is None for f in missing_fields)]
        if not needs:
            continue
        mfrs = sorted({str(p.get("mfr") or "") for p in needs})
        sers = sorted({str(p.get("series") or "") for p in needs if p.get("series")})
        work.append({
            "parts_unblocked": len(needs),
            "manufacturer": "; ".join(mfrs)[:60],
            "series": "; ".join(sers)[:60],
            "datasheet_url": url,
            "example_parts": ", ".join(str(p.get("part_number")) for p in needs[:4]),
        })
    work.sort(key=lambda d: -d["parts_unblocked"])
    return work, {"unlinked_parts": len(unlinked),
                  "unlinked_by_mfr": collections.Counter(
                      str(p.get("mfr") or "") for p in unlinked).most_common(6)}


def _report(name: str, rows: list[dict], fields: list[str]) -> list[dict]:
    work, extra = _worklist(rows, fields)
    total = len(rows)
    covered = sum(w["parts_unblocked"] for w in work)
    print(f"\n=== {name}: {total} parts, {len(work)} datasheets to read")
    print(f"    {covered} parts are reachable through a datasheet link; "
          f"{extra['unlinked_parts']} have no usable link at all")
    if extra["unlinked_parts"]:
        print(f"    unlinked by manufacturer: {extra['unlinked_by_mfr']}")
        print(f"    -> {name} has a CEILING of {100.0*covered/total:.0f}% of the catalogue "
              f"until those links are sourced separately")
    cum = 0
    print(f"\n    {'#':>3} {'parts':>6} {'cum%':>6}  manufacturer / series")
    for i, w in enumerate(work[:15], 1):
        cum += w["parts_unblocked"]
        label = (w["manufacturer"] + (" / " + w["series"] if w["series"] else ""))[:58]
        print(f"    {i:3} {w['parts_unblocked']:6} {100.0*cum/max(covered,1):5.1f}%  {label}")
    for n_pct in (0.5, 0.8):
        c = 0
        for k, w in enumerate(work, 1):
            c += w["parts_unblocked"]
            if c >= n_pct * covered:
                print(f"    -> {k} datasheets cover {int(n_pct*100)}% of the reachable parts")
                break
    return work


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    jobs = [
        # A1 has the best leverage of the three AND no ceiling: every part carries a link.
        ("NTC  (PENDING A1 — pulse energy / max switchable C)", DB.ingest(),
         ["energy_J", "max_switch_uF"], "A1_NTC_datasheet_worklist.csv"),
        ("MOV  (PENDING A2 — Vc @ In)", DB.ingest_mov(), ["vc_imax"], "A2_MOV_datasheet_worklist.csv"),
        ("GDT  (PENDING A3 — impulse sparkover, follow current)", DB.ingest_gdt(),
         ["v_impulse_spark", "follow_current"], "A3_GDT_datasheet_worklist.csv"),
    ]
    for name, rows, fields, fname in jobs:
        work = _report(name, rows, fields)
        path = os.path.join(OUT_DIR, fname)
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(work[0].keys()) if work else
                               ["parts_unblocked", "manufacturer", "series",
                                "datasheet_url", "example_parts"])
            w.writeheader()
            w.writerows(work)
        print(f"    written: {os.path.normpath(path)}")
    print("\nThe fields land in the workbooks as new columns. Any of these headers is read:\n"
          "    NTC : 'Pulse energy (J)'  or  'Max switchable C (uF)' + 'Switching voltage (V)'\n"
          "    MOV : 'Vc @ In (V)'\n"
          "    GDT : 'Impulse Sparkover (V)'  and  'Follow Current (A)'\n"
          "A blank or '-' stays DATA MISSING, which is correct - never enter a guessed value.\n"
          "For the NTC either form is a REAL rating: max switchable capacitance converts exactly,\n"
          "E = 1/2 C V^2, so a part publishing only that is not a gap (C284).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
