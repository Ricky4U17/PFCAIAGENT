"""
app/magnetics/schema.py
Single source of truth for what every material JSON must contain.

Rules:
  - Adding a new FIELD: add it here → validator catches missing fields at load time
  - Adding a new MATERIAL TYPE: add its schema here → generator builds correct template
  - Never validate inside data_loader or step7 — always go through MagneticsDB.validate()
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

MaterialType = Literal["ferrite", "powder"]
DataQuality  = Literal[
    "digitized",                    # manually digitized from datasheet graphs (best)
    "steinmetz_fitted_to_datasheet",# Steinmetz params fitted to datasheet curves
    "published_anchor_points",      # anchored to specific published values
    "anchored_to_reference_step13", # anchored to our reference design Step 13
    "magnetics_application_note",   # from published application note
    "estimated",                    # estimated from material rankings / scaling
    "pdf_extracted",                # extracted from PDF via Claude API
    "custom_entered",               # entered manually by designer
]

# ── Schema field definitions ──────────────────────────────────────────────────
# Each entry: (field_path, type_hint, required, valid_range, description)
FERRITE_REQUIRED_FIELDS = [
    ("supplier",               str,   True,  None,         "Material supplier name"),
    ("grade",                  str,   True,  None,         "Grade designation e.g. 3C95"),
    ("type",                   str,   True,  None,         "Must be 'ferrite'"),
    ("data_source",            str,   True,  None,         "Datasheet or application note reference"),
    ("data_quality",           str,   True,  None,         "One of DataQuality literals"),
    ("basic.mu_initial",       float, True,  (100, 20000), "Initial relative permeability"),
    ("basic.curie_temp_C",     float, True,  (100, 400),   "Curie temperature °C"),
    ("steinmetz_25C.Pv_ref_kW_m3", float, True, (0.1, 2000), "Loss density at ref point 25°C kW/m³"),
    ("steinmetz_25C.f_ref_kHz",    float, True, (1, 1000),   "Reference frequency kHz"),
    ("steinmetz_25C.B_ref_T",      float, True, (0.01, 0.5), "Reference flux density T"),
    ("steinmetz_25C.alpha",        float, True, (0.8, 2.0),  "Frequency exponent"),
    ("steinmetz_25C.beta",         float, True, (1.5, 4.0),  "Flux density exponent"),
    ("steinmetz_100C.Pv_ref_kW_m3",float, True, (0.1, 2000), "Loss density 100°C kW/m³"),
    ("Bsat_vs_T.T_C",              list,  True,  None,        "Temperature points °C"),
    ("Bsat_vs_T.Bsat",             list,  True,  None,        "Bsat values T — must all be 0.2–0.7T"),
    ("mu_r_vs_T.T_C",              list,  True,  None,        "Temperature points °C"),
    ("mu_r_vs_T.mu_r",             list,  True,  None,        "µr values — must all be 500–20000"),
    ("core_loss_surface_25C.f_kHz",list,  True,  None,        "Frequency axis kHz"),
    ("core_loss_surface_25C.B_pk_T",list, True,  None,        "Bpk axis T"),
    ("core_loss_surface_25C.Pv_kW_m3",list, True, None,      "Loss table rows×cols kW/m³"),
    ("core_loss_surface_100C.Pv_kW_m3",list, True, None,     "Loss table at 100°C"),
]

POWDER_REQUIRED_FIELDS = [
    ("supplier",               str,   True,  None,         "Material supplier name"),
    ("material_line",          str,   True,  None,         "Product line e.g. Kool Mu"),
    ("mu_initial",             float, True,  (10, 600),    "Initial permeability"),
    ("type",                   str,   True,  None,         "Must be 'powder'"),
    ("data_source",            str,   True,  None,         "Reference"),
    ("data_quality",           str,   True,  None,         "One of DataQuality literals"),
    ("basic.Bsat_T",           float, True,  (0.5, 2.0),   "Approximate saturation flux T"),
    ("basic.AL_tolerance_pct", float, True,  (1, 20),      "AL tolerance %"),
    ("steinmetz_25C.Pv_ref_kW_m3", float, True, (10, 5000), "Loss density kW/m³"),
    ("steinmetz_25C.alpha",        float, True, (0.8, 2.0),  "Frequency exponent"),
    ("steinmetz_25C.beta",         float, True, (1.5, 4.0),  "Flux density exponent"),
    ("dc_bias_rolloff.H_Oe",       list,  True,  None,        "H axis in Oersteds"),
    ("dc_bias_rolloff.mu_pct",     list,  True,  None,        "µ_eff/µ_initial × 100 (0–100%)"),
    ("core_loss_surface_25C.f_kHz",list,  True,  None,        "Frequency axis kHz"),
    ("core_loss_surface_25C.B_pk_T",list, True,  None,        "Bpk axis T"),
    ("core_loss_surface_25C.Pv_kW_m3",list, True, None,      "Loss table kW/m³"),
]

BUSINESS_RULES = {
    "ferrite": [
        ("Bsat@100C must be 0.25–0.65T",
         lambda d: 0.25 <= min(d.get("Bsat_vs_T",{}).get("Bsat",[0.4])) <= 0.65),
        ("Steinmetz alpha must be 1.0–1.8",
         lambda d: 1.0 <= d.get("steinmetz_25C",{}).get("alpha",1.25) <= 1.8),
        ("Steinmetz beta must be 2.0–3.5",
         lambda d: 2.0 <= d.get("steinmetz_25C",{}).get("beta",2.5) <= 3.5),
        ("Pv_100C must be >= Pv_25C (loss increases with temperature)",
         lambda d: (d.get("steinmetz_100C",{}).get("Pv_ref_kW_m3",999) >=
                    d.get("steinmetz_25C",{}).get("Pv_ref_kW_m3",0))),
        ("Bsat_vs_T must be monotonically decreasing with temperature",
         lambda d: all(
             d["Bsat_vs_T"]["Bsat"][i] >= d["Bsat_vs_T"]["Bsat"][i+1]
             for i in range(len(d["Bsat_vs_T"]["Bsat"])-1)
         ) if "Bsat_vs_T" in d and len(d["Bsat_vs_T"].get("Bsat",[])) > 1 else True),
        ("core_loss_surface grids must be non-empty (at least 3×3)",
         lambda d: (len(d.get("core_loss_surface_25C",{}).get("f_kHz",[])) >= 3 and
                    len(d.get("core_loss_surface_25C",{}).get("B_pk_T",[])) >= 3)),
    ],
    "powder": [
        ("Bsat must be 0.5–2.0T",
         lambda d: 0.5 <= d.get("basic",{}).get("Bsat_T",1.0) <= 2.0),
        ("DC bias rolloff: mu_pct[0] must be ~100",
         lambda d: d.get("dc_bias_rolloff",{}).get("mu_pct",[100])[0] >= 95),
        ("DC bias rolloff: mu_pct must be monotonically decreasing",
         lambda d: all(
             d["dc_bias_rolloff"]["mu_pct"][i] >= d["dc_bias_rolloff"]["mu_pct"][i+1]
             for i in range(len(d["dc_bias_rolloff"]["mu_pct"])-1)
         ) if "dc_bias_rolloff" in d and len(d["dc_bias_rolloff"].get("mu_pct",[])) > 1 else True),
        ("DC bias rolloff: H_Oe must be monotonically increasing",
         lambda d: all(
             d["dc_bias_rolloff"]["H_Oe"][i] < d["dc_bias_rolloff"]["H_Oe"][i+1]
             for i in range(len(d["dc_bias_rolloff"]["H_Oe"])-1)
         ) if "dc_bias_rolloff" in d and len(d["dc_bias_rolloff"].get("H_Oe",[])) > 1 else True),
        ("mu_initial must be 10–600",
         lambda d: 10 <= d.get("mu_initial",60) <= 600),
    ]
}

# ── PDF extraction target fields (what the extractor is asked to find) ────────
PDF_EXTRACTION_TARGETS = {
    "ferrite": {
        "basic": {
            "mu_initial":        {"unit": "dimensionless", "hint": "Initial relative permeability, typically 1000-5000"},
            "curie_temp_C":      {"unit": "°C",  "hint": "Curie temperature Tc"},
        },
        "Bsat_vs_T": {
            "description": "Saturation flux density vs temperature. Look for graph or table titled 'Bsat vs T' or 'B-H curve at different temperatures'",
            "T_C":  {"unit": "°C",  "hint": "Temperature axis points e.g. [25, 60, 80, 100, 120]"},
            "Bsat": {"unit": "T",   "hint": "Bsat values at H=1200 A/m e.g. [0.51, 0.47, 0.45, 0.43, 0.39]"},
        },
        "steinmetz": {
            "description": "Core loss parameters. Look for graphs titled 'Specific power loss' or 'Pv vs B' at multiple frequencies",
            "Pv_ref_kW_m3": {"unit": "kW/m³", "hint": "Power loss density at reference point"},
            "f_ref_kHz":    {"unit": "kHz",    "hint": "Reference frequency for Steinmetz fit"},
            "B_ref_T":      {"unit": "T",      "hint": "Reference B for Steinmetz fit"},
            "alpha":        {"unit": None,      "hint": "Frequency exponent, typically 1.2-1.3"},
            "beta":         {"unit": None,      "hint": "Flux density exponent, typically 2.4-2.7"},
            "T_C":          {"unit": "°C",      "hint": "Temperature at which parameters apply"},
        },
        "mu_r_vs_T": {
            "description": "Permeability vs temperature curve",
            "T_C":  {"unit": "°C"},
            "mu_r": {"unit": "dimensionless"},
        },
        "core_loss_table": {
            "description": "If a table of Pv values at different f and B is provided, extract the full grid",
            "f_values_kHz": {"unit": "kHz", "hint": "All frequency values on the table/chart"},
            "B_values_T":   {"unit": "T",   "hint": "All Bpk values on the table/chart"},
            "Pv_matrix":    {"unit": "kW/m³ or mW/cm³", "hint": "Loss values for each (f,B) combination"},
        }
    },
    "powder": {
        "basic": {
            "mu_initial":    {"unit": None, "hint": "Initial permeability, e.g. 60, 125, 200"},
            "Bsat_T":        {"unit": "T",  "hint": "Saturation flux density, typically 0.75-1.6T for powder cores"},
        },
        "dc_bias_rolloff": {
            "description": "Permeability vs DC bias curve. Look for graph titled 'Permeability vs DC Bias' or '% of Initial Permeability vs Oersteds'",
            "H_Oe":   {"unit": "Oe",  "hint": "DC bias field in Oersteds, x-axis of curve"},
            "mu_pct": {"unit": "%",   "hint": "% of initial permeability, y-axis (0-100%)"},
        },
        "core_loss": {
            "description": "Core loss density. Look for graph titled 'Core Loss' or 'Loss Density'",
            "Pv_ref":   {"unit": "mW/cm³", "hint": "Reference loss value at a specific f and B"},
            "f_ref_kHz":{"unit": "kHz"},
            "B_ref_T":  {"unit": "T"},
            "alpha":    {"unit": None, "hint": "Frequency exponent"},
            "beta":     {"unit": None, "hint": "Flux density exponent"},
        }
    }
}

# ── Template generators ───────────────────────────────────────────────────────
def ferrite_template(supplier: str, grade: str) -> dict:
    """Generate a blank ferrite JSON template for manual filling."""
    return {
        "supplier": supplier, "grade": grade, "type": "ferrite",
        "data_source": "FILL: datasheet URL or reference",
        "data_quality": "custom_entered",
        "basic": {
            "mu_initial": 0,  "mu_initial_tolerance_pct": 25,
            "curie_temp_C": 0, "resistivity_ohm_m": 5.0
        },
        "Bsat_vs_T": {
            "description": "Bsat (T) at H=1200 A/m vs temperature. FILL with datasheet values.",
            "T_C":  [25, 60, 80, 100, 120],
            "Bsat": [0.0, 0.0, 0.0, 0.0, 0.0]
        },
        "mu_r_vs_T": {
            "T_C":  [25, 60, 80, 100, 120],
            "mu_r": [0, 0, 0, 0, 0]
        },
        "steinmetz_25C": {
            "Pv_ref_kW_m3": 0.0, "f_ref_kHz": 100, "B_ref_T": 0.10,
            "alpha": 0.0, "beta": 0.0,
            "note": "FILL: fitted to datasheet Pv vs B curves at 25°C"
        },
        "steinmetz_100C": {
            "Pv_ref_kW_m3": 0.0, "f_ref_kHz": 100, "B_ref_T": 0.10,
            "alpha": 0.0, "beta": 0.0,
            "note": "FILL: at 100°C. Pv_ref_100C must be >= Pv_ref_25C."
        },
        "core_loss_surface_25C": {
            "T_C": 25, "f_kHz": [25,50,70,100,200,300,500,1000],
            "B_pk_T": [0.005,0.010,0.020,0.050,0.080,0.100,0.150,0.200,0.300,0.400],
            "Pv_kW_m3": "FILL: 2D table, rows=B, cols=f",
            "note": "kW/m³. Agent will compute from Steinmetz if table not provided."
        },
        "core_loss_surface_100C": {
            "T_C": 100, "Pv_kW_m3": "FILL: same grid as 25C table"
        }
    }

def powder_template(supplier: str, material_line: str, mu: int) -> dict:
    """Generate a blank powder core JSON template for manual filling."""
    return {
        "supplier": supplier, "material_line": material_line, "mu_initial": mu,
        "type": "powder",
        "data_source": "FILL: datasheet or application note reference",
        "data_quality": "custom_entered",
        "basic": {
            "Bsat_T": 0.0, "temp_coeff_AL_ppm_C": 150, "AL_tolerance_pct": 8,
            "note": "FILL: Bsat at saturation onset (approximate for powder cores)"
        },
        "dc_bias_rolloff": {
            "description": "µ_eff/µ_initial (%) vs H (Oe). Source: FILL with datasheet reference.",
            "x_unit": "Oe",
            "H_Oe":   [0, 10, 20, 30, 50, 80, 100, 150, 200, 300, 500, 800],
            "mu_pct": [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "data_quality": "custom_entered",
            "note": "FILL: digitize from datasheet 'Permeability vs DC Bias' graph"
        },
        "steinmetz_25C": {
            "Pv_ref_kW_m3": 0.0, "f_ref_kHz": 100, "B_ref_T": 0.10,
            "alpha": 0.0, "beta": 0.0,
            "note": "FILL: from datasheet core loss curves at 25°C"
        },
        "core_loss_surface_25C": {
            "T_C": 25, "f_kHz": [10,25,50,70,100,200,300,500,1000],
            "B_pk_T": [0.005,0.010,0.020,0.050,0.100,0.150,0.200,0.300,0.500],
            "Pv_kW_m3": "FILL: 2D table, rows=B, cols=f. Agent computes from Steinmetz if omitted.",
            "note": "kW/m³."
        }
    }
