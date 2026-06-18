#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adapter_template.py
===================
SKELETON for the bigger script's adapter:  DB record + designer selection  ->  package dict.

This file is the ONE place where your database's native field names, units, and
single-core-vs-stack conventions get mapped onto the frozen package contract consumed by
both `pfc_inductor_engine.py` (Python) and `SimAgentField` (browser). The engine and the
viewer never change for a schema difference - only this adapter does. After the merge
settles, renaming the contract to match your DB natively is a refactor of THIS file only.

HOW TO USE
----------
1. Replace every `REC("...")` / `SEL("...")` placeholder with your real DB column /
   selection-field access. Each line states the REQUIRED UNIT and BASIS - convert here.
2. Run:  python adapter_template.py            (uses the built-in smoke record)
         python adapter_template.py db.json    (your exported record, once mapped)
   It validates the produced package and prints errors/warnings. Zero errors = the
   adapter is producing a contract-conformant package (pre-merge Phase 2).
3. See DATA_DICTIONARY.md for every field's unit, basis, source, and failure mode.

THE THREE CLASSIC MIXING TRAPS (guard deliberately):
  * BASIS   - Ae/Ve/AL/HT are PER SINGLE CORE; the engine multiplies by `stacks`.
              If your DB stores stack totals, DIVIDE here.
  * UNITS   - mm / mm^2 / mm^3 / nH / T / Oe / ohm / Hz. Steinmetz f in kHz, B in T.
  * eta vs eta*PF - operating.points carries eta and PF SEPARATELY;
              maps.etaByVin is the PRODUCT eta*PF. validate() cross-checks them.
"""
from __future__ import annotations
import json, sys
import pfc_inductor_engine as eng


# ---------------------------------------------------------------------------------------
def build_package(db_record: dict, selection: dict, operating: list, acceptance: dict,
                  measured: dict | None = None, fields: dict | None = None) -> dict:
    """
    db_record  : the core/material/wire row(s) your DB returns for the designer's choice
    selection  : designer's finalized choices (N, stacks, Vout, fsw, nph, ambient, ...)
    operating  : list of spec corners [{Vin, Pout, eta, PF}, ...] from the converter spec
    acceptance : upstream pass/fail limits (ONLY what your spec defines; nothing invented)
    measured   : optional bench data (DCR, core loss, L(I)) from the DB's real-world tables
    fields     : optional solved FEA/CFD ROM from the FEA-gate agent
    """
    # Two helper aliases so every TODO is greppable. Replace the lookups with your schema.
    REC = lambda k: db_record[k]      # TODO: adapt to your DB row access (and convert units!)
    SEL = lambda k: selection[k]      # TODO: adapt to your selection-record access

    pkg = {
        "schemaVersion": "1.0",
        "meta": {
            "units": "SI+catalog",
            "provenance": "built by adapter from main-script DB",   # keep honest & traceable
            "source_ids": {                                          # TODO: your DB keys for audit
                "core": REC("core_part_number"),
                "material": REC("material_id"),
                "wire": REC("wire_id"),
            },
        },
        "model": {
            "design": {
                "Vout": SEL("Vout_V"),                 # V
                "fsw": SEL("fsw_Hz"),                  # Hz  (NOT kHz - convert if DB stores kHz)
                "lineHz": SEL("line_Hz"),              # Hz (50/60)
                "nph": SEL("n_phases"),                # interleaved phase count
                # optional, only if the browser explorer should derive load envelopes:
                "Prated": SEL("Prated_W"),             # W total
                "specLowLineMaxPct": SEL("lowline_max_pct"),   # % of Prated allowed <=132 V
                "specHighLineMaxPct": SEL("highline_max_pct"), # % of Prated allowed >=180 V
            },
            "environment": {
                "Tamb_C": SEL("Tamb_C"),               # degC worst-case ambient
                "Thot_C": SEL("Thot_max_C"),           # degC allowed hotspot (optional)
            },
            "winding": {
                "N": SEL("turns"),                     # turns (integer)
                "stacks": SEL("stack_count"),          # cores stacked (integer, >=1)
                "build_mm": SEL("winding_build_mm"),   # mm radial build (optional; default 3.8)
            },
            "geometry": {                              # !!! ALL PER SINGLE CORE !!!
                "OD_mm": REC("od_mm"),                 # mm outer diameter
                "ID_mm": REC("id_mm"),                 # mm inner diameter
                "HT_mm": REC("ht_mm"),                 # mm height of ONE core (not the stack)
                "Ae_mm2": REC("ae_mm2"),               # mm^2 effective area of ONE core
                "Le_mm": REC("le_mm"),                 # mm magnetic path length
                "Ve_mm3": REC("ve_mm3"),               # mm^3 volume of ONE core (or pass Ve_cm3)
                "Wa_mm2": REC("window_area_mm2"),      # mm^2 window area
                "AL_nH": REC("al_nH"),                 # nH/T^2 of ONE core at zero bias
                "AL_tol": REC("al_tol_frac"),          # fraction, e.g. 0.08 for +-8 %
            },
            "material": {
                "name": REC("material_name"),
                "Bsat": REC("bsat_T"),                 # T
                # core loss: P[mW/cm^3] = a * B[T]^b * f[kHz]^c   <-- f in kHz!
                "steinmetz": {"a": REC("loss_a"), "b": REC("loss_b"), "c": REC("loss_c")},
                # DC bias: %mu = 1/(k0 + k1*H[Oe]^p)              <-- H in Oersted!
                "retention": {"k0": REC("bias_a"), "k1": REC("bias_b"), "p": REC("bias_c")},
                "lossMaxScale": REC("loss_max_scale"), # catalog max/typ band (e.g. 1.286)
                # optional transcription anchors straight from the datasheet (recommended):
                # "anchors": {"loss": [B_T, f_kHz, P_mWcm3], "bias": [[H_Oe, pct_mu], ...]},
                # optional REAL-WORLD (Tier-3) bench data from your DB:
                "measured": (measured or {}).get("material", {}),
                # shape: {"coreLoss": {"steinmetz":{a,b,c}, "maxScale":1.05}  OR
                #                     {"points": [[B_T,f_kHz,P_mWcm3], ...>=3]},
                #         "inductance": {"H_Oe":[...], "L_uH":[...]}  or  {"I_A":[...], "L_uH":[...]}}
            },
            "copper": {
                "wire": {
                    "type": REC("wire_type"),          # 'litz' | 'magnet' | 'solid'
                    "strands": REC("strand_count"),    # per bundle
                    "strandDia_mm": REC("strand_dia_mm"),  # mm BARE copper diameter
                    "parallel": SEL("parallel_bundles"),   # bundles in parallel (>=1)
                    "fillFactor": REC("bundle_fill_factor"),  # optional
                },
                # Tier-3 measured DCR from your DB (either form). Geometry estimate cross-checks it.
                "measured": (measured or {}).get("copper", {}),   # {"RdcTotal_20C": ohm} etc.
                "alphaCu": 0.00393, "rho20_ohm_m": 1.724e-8,      # override only if you must
            },
            "cooling": {"mode": SEL("cooling_mode"),   # 'natural' | 'forced'
                        "airflow_mps": SEL("airflow_mps")},       # only used when forced
            # Browser-explorer maps. Generate the PRODUCT from the same operating points so the
            # two representations can never disagree (validate() cross-checks them):
            "maps": {"etaByVin": {int(p["Vin"]): round(p["eta"] * p["PF"], 4) for p in operating},
                     "crestByVin": {}},
        },
        "operating": {"points": operating},
        "acceptance": acceptance,                      # ONLY upstream limits; omit = not checked
    }
    if fields:
        pkg["fields"] = fields                         # solved FEA/CFD ROM (Tier-2), if available
    return pkg


# ---------------------------------------------------------------------------------------
def _smoke():
    """Built-in smoke record proving the adapter SHAPE; replace with one real DB export."""
    db_record = dict(core_part_number="DEMO-CORE", material_id="DEMO-MAT", wire_id="DEMO-WIRE",
                     od_mm=58.04, id_mm=34.75, ht_mm=14.86, ae_mm2=144.0, le_mm=143.0,
                     ve_mm3=20700.0, window_area_mm2=948.0, al_nH=94.0, al_tol_frac=0.08,
                     material_name="DemoAlloy", bsat_T=1.5,
                     loss_a=121.47, loss_b=2.263, loss_c=1.403,
                     bias_a=0.01, bias_b=1.58e-9, bias_c=3.067, loss_max_scale=1.286,
                     wire_type="litz", strand_count=800, strand_dia_mm=0.1, bundle_fill_factor=0.45)
    selection = dict(Vout_V=394.0, fsw_Hz=70e3, line_Hz=60.0, n_phases=2, Prated_W=3600.0,
                     lowline_max_pct=47.2, highline_max_pct=100.0, Tamb_C=50.0, Thot_max_C=110.0,
                     turns=31, stack_count=3, winding_build_mm=3.8, parallel_bundles=2,
                     cooling_mode="natural", airflow_mps=0.0)
    operating = [{"Vin": 180, "Pout": 3600, "eta": 0.965, "PF": 0.9889},
                 {"Vin": 230, "Pout": 3600, "eta": 0.988, "PF": 0.9789},
                 {"Vin": 90,  "Pout": 1700, "eta": 0.945, "PF": 0.9987}]
    acceptance = {"L_target_uH": 239.0, "sat_margin_min": 0.43, "FFcu_limit": 0.45, "J_max": 7.0}
    return build_package(db_record, selection, operating, acceptance)


if __name__ == "__main__":
    pkg = (json.load(open(sys.argv[1])) if len(sys.argv) > 1 else _smoke())
    if len(sys.argv) > 1 and "model" not in pkg:
        print("NOTE: file is a raw DB export, not a package; map it via build_package() first.")
        sys.exit(2)
    vr = eng.validate(pkg)
    print("validate:", "OK" if vr.ok else "ERRORS")
    for e in vr.errors:   print("  ERROR  :", e)
    for w in vr.warnings: print("  WARNING:", w)
    if vr.ok:
        r = eng.compute(pkg)
        print(f"compute : verdict={r['verdict']}  Lguar={r['worst']['Lmin_guarantee_uH']:.0f} uH  "
              f"worstLoss={r['worst']['loss']['Ptot_max']:.2f} W  tiers={r['tier']}")
    sys.exit(0 if vr.ok else 1)
