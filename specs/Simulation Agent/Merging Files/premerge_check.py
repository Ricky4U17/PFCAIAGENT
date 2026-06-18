#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
premerge_check.py — run IN THE MERGE ENVIRONMENT at pre-merge time.

Automates Phases 0, 1 and 4 of PREMERGE_CHECKLIST.md; `--package file.json` adds the
Phase-2 validation of your real adapted package. Phases 3 and 5 (golden cross-check,
designer demo) are human steps — see the checklist.

Usage:
    python premerge_check.py
    python premerge_check.py --package real_pkg.json
    python premerge_check.py --html pfc_sim_agent_v14.html      # if viewer moved/renamed

Exit code 0 = all run phases PASS (SKIPs allowed, printed loudly). Nonzero = FAIL.
"""
from __future__ import annotations
import argparse, importlib, json, os, shutil, subprocess, sys, tempfile, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []

def report(phase: str, status: str, msg: str):
    results.append((phase, status, msg))
    print(f"[{status}] {phase}: {msg}")

# ------------------------------------------------------------------ Phase 0
def phase0():
    ok = True
    v = sys.version_info
    if v < (3, 9):
        report("0 env/python", FAIL, f"Python {v.major}.{v.minor} < 3.9"); ok = False
    else:
        report("0 env/python", PASS, f"Python {v.major}.{v.minor}.{v.micro}")
    try:
        import numpy as np
        report("0 env/numpy", PASS, np.__version__)
    except Exception as e:
        report("0 env/numpy", FAIL, str(e)); return False
    try:
        sys.path.insert(0, HERE)
        eng = importlib.import_module("pfc_inductor_engine")
        sch = eng.schema()
        report("0 env/engine", PASS, f"v{getattr(eng,'__version__','?')} schema v{sch['schemaVersion']}")
    except Exception as e:
        report("0 env/engine", FAIL, f"import/schema failed: {e}"); ok = False
    return ok

# ------------------------------------------------------------------ Phase 1
def _fallback_runner() -> tuple[int, int]:
    """Run the test functions without pytest (shim for approx/raises)."""
    import math, types
    class _Approx:
        def __init__(s, v, rel=1e-6): s.v, s.rel = v, rel
        def __eq__(s, o): return abs(o - s.v) <= s.rel * abs(s.v) + 1e-12
    class _Raises:
        def __init__(s, exc): s.exc, s.value = exc, None
        def __enter__(s): return s
        def __exit__(s, et, ev, tb):
            if et is None: raise AssertionError("expected " + s.exc.__name__)
            if issubclass(et, s.exc): s.value = ev; return True
            return False
    fake = types.ModuleType("pytest")
    fake.approx = lambda v, rel=1e-6, **k: _Approx(v, rel)
    fake.raises = lambda e: _Raises(e); fake.main = lambda a: 0
    sys.modules.setdefault("pytest", fake)
    T = importlib.import_module("test_pfc_inductor_engine"); importlib.reload(T)
    tests = [(n, f) for n, f in vars(T).items() if n.startswith("test_") and callable(f)]
    fails = 0
    for n, f in tests:
        try: f()
        except Exception:
            fails += 1; print(f"    FAIL {n}"); traceback.print_exc(limit=2)
    return len(tests), fails

def phase1():
    ok = True
    # test suite
    try:
        import pytest  # noqa
        rc = subprocess.run([sys.executable, "-m", "pytest",
                             os.path.join(HERE, "test_pfc_inductor_engine.py"), "-q"],
                            capture_output=True, text=True)
        last = (rc.stdout.strip().splitlines() or ["?"])[-1]
        report("1 tests(pytest)", PASS if rc.returncode == 0 else FAIL, last)
        ok &= rc.returncode == 0
    except ImportError:
        n, f = _fallback_runner()
        report("1 tests(fallback)", PASS if f == 0 else FAIL, f"{n - f}/{n} passed (pytest not installed)")
        ok &= f == 0
    # fixtures
    import pfc_inductor_engine as eng
    expect = {"example_package_analytic.json": ("APPROVE", "analytic"),
              "example_package_fea.json": ("APPROVE", "fea")}
    for name, (verd, prov) in expect.items():
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            report(f"1 fixture/{name}", FAIL, "missing"); ok = False; continue
        try:
            r = eng.compute(json.load(open(p)))
            good = r["verdict"] == verd and r["provenance"]["windingAC"] == prov
            report(f"1 fixture/{name}", PASS if good else FAIL,
                   f"verdict={r['verdict']} windingAC={r['provenance']['windingAC']}")
            ok &= good
        except Exception as e:
            report(f"1 fixture/{name}", FAIL, str(e)); ok = False
    # retired legacy must not be importable
    legacy = os.path.join(HERE, "powder_core_inductor.py")
    if os.path.exists(legacy):
        try:
            importlib.import_module("powder_core_inductor")
            report("1 legacy-stub", FAIL, "powder_core_inductor imported WITHOUT error (embedded materials risk)")
            ok = False
        except ImportError:
            report("1 legacy-stub", PASS, "retired stub raises ImportError as designed")
    else:
        report("1 legacy-stub", PASS, "legacy file already deleted")
    return ok

# ------------------------------------------------------------------ Phase 2 (optional)
def phase2(pkg_path: str):
    import pfc_inductor_engine as eng
    try:
        pkg = json.load(open(pkg_path))
    except Exception as e:
        report("2 package/load", FAIL, f"{pkg_path}: {e}"); return False
    vr = eng.validate(pkg)
    for w in vr.warnings: print("    WARNING:", w)
    for e in vr.errors:   print("    ERROR  :", e)
    if not vr.ok:
        report("2 package/validate", FAIL, f"{len(vr.errors)} error(s) — fix the ADAPTER (units/basis)")
        return False
    r = eng.compute(pkg)
    report("2 package/validate", PASS,
           f"verdict={r['verdict']} warnings={len(vr.warnings)} (each must be explained!) tiers={r['tier']}")
    return True

# ------------------------------------------------------------------ Phase 4
HARNESS = r"""
const doc={getElementById:()=>null,querySelectorAll:()=>[]};
global.window={document:doc,addEventListener(){}};global.document=doc;
eval(require('fs').readFileSync(process.argv[2],'utf8'));
const pkg=JSON.parse(require('fs').readFileSync(process.argv[3],'utf8'));
const r=window.SimAgentField.evaluateHeadless(pkg,{vin:180,loadPct:100});
console.log(JSON.stringify({verdict:r.acceptance.verdict,prov:r.provenance,ok:r.validation.ok}));
"""

def phase4(html_path: str, extra_pkgs: list[str]):
    node = shutil.which("node")
    if not node:
        report("4 parity", SKIP, "node not found — run browser parity manually per checklist")
        return True
    if not os.path.exists(html_path):
        report("4 parity", FAIL, f"viewer not found: {html_path}"); return False
    import re, pfc_inductor_engine as eng
    html = open(html_path, encoding="utf-8").read()
    js = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
    ok = True
    with tempfile.TemporaryDirectory() as td:
        jsf = os.path.join(td, "viewer.js"); open(jsf, "w").write(js)
        hf = os.path.join(td, "h.js"); open(hf, "w").write(HARNESS)
        pkgs = ["example_package_analytic.json", "example_package_fea.json"] + extra_pkgs
        for name in pkgs:
            p = name if os.path.isabs(name) else os.path.join(HERE, name)
            if not os.path.exists(p): continue
            rE = eng.compute(json.load(open(p)))
            out = subprocess.run([node, hf, jsf, p], capture_output=True, text=True)
            if out.returncode != 0:
                report(f"4 parity/{os.path.basename(p)}", FAIL, out.stderr.strip()[:160]); ok = False; continue
            rB = json.loads(out.stdout.strip().splitlines()[-1])
            match = (rE["verdict"] == rB["verdict"])
            report(f"4 parity/{os.path.basename(p)}", PASS if match else FAIL,
                   f"engine={rE['verdict']} browser={rB['verdict']}")
            ok &= match
    return ok

# ------------------------------------------------------------------ main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", help="real adapted package JSON (Phase 2)")
    ap.add_argument("--html", default=os.path.join(HERE, "pfc_sim_agent_v14.html"))
    a = ap.parse_args()
    print("=== PRE-MERGE CHECK (run in the merge environment) ===")
    ok = phase0()
    ok = phase1() and ok
    if a.package: ok = phase2(a.package) and ok
    ok = phase4(a.html, [a.package] if a.package else []) and ok
    print("\n=== SUMMARY ===")
    for ph, st, msg in results: print(f"  [{st}] {ph} — {msg}")
    skips = sum(1 for _, s, _ in results if s == SKIP)
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}"
          + (f"  ({skips} SKIP — complete manually per checklist)" if skips else "")
          + "\nPhases 3 (golden cross-check) and 5 (designer demo) are manual — see PREMERGE_CHECKLIST.md")
    sys.exit(0 if ok else 1)
