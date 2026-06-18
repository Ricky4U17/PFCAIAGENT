"""
backend/app/mode_b/step15_capacitor.py
Step 15 — Vout Capacitor calculation engine.
Implements Steps 15.1–15.8 per spec.
"""
from __future__ import annotations
import io, json, math, os, re
from typing import Optional

_HERE    = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, "data", "cap_database.json")

_CAP_DB: dict | None = None

def _load_db() -> dict:
    global _CAP_DB
    if _CAP_DB is None:
        with open(_DB_PATH, encoding="utf-8") as f:
            _CAP_DB = json.load(f)
    return _CAP_DB


def _interp_esr(esr_db: dict, val_uF: int, vrating: int) -> Optional[float]:
    """Return ESR (mΩ) for val_uF at vrating, interpolating if exact not in DB."""
    vkey = str(vrating)
    # Exact match
    exact = esr_db.get(str(val_uF), {})
    if vkey in exact:
        return float(exact[vkey])
    # Collect known (C, ESR) pairs at this voltage rating
    pts = []
    for c_key, v_dict in esr_db.items():
        if vkey in v_dict:
            try:
                pts.append((int(c_key), float(v_dict[vkey])))
            except (ValueError, TypeError):
                pass
    if len(pts) < 2:
        return None
    # Fit K = ESR × C (log-linear relationship)
    K = sum(c * e for c, e in pts) / len(pts)
    return K / val_uF if val_uF > 0 else None


# ── Step 15.2 + 15.3 + 15.6 per operating point ──────────────────────────────

def calc_operating_point(
    Vin_rms: float, Pout: float, eta: float,
    Vout: float, f_line: float,
    Vdc_ripple: float, Vdc_min: float, t_hold_s: float,
) -> dict:
    """Full Step 15 calc for one operating point."""
    Vin_pk  = math.sqrt(2) * Vin_rms

    # Step 15.6 — RMS currents
    I_dc    = Pout / (eta * Vout)
    I_LF    = I_dc / math.sqrt(2)
    denom   = 6 * Vin_pk * 2 * math.pi
    I_HF    = math.sqrt(max(0.0, I_dc**2 * 16 * Vout / denom - I_LF**2)) if denom > 0 else 0.0
    I_total = math.sqrt(I_LF**2 + I_HF**2)

    # Step 15.2 — hold-up capacitance
    C_holdup_F  = (2 * Pout * t_hold_s) / (Vout**2 - Vdc_min**2)

    # Step 15.3 — ripple capacitance
    C_ripple_F  = Pout / (2 * math.pi * f_line * eta * Vout * Vdc_ripple)

    return {
        "Vin_rms":      Vin_rms,
        "Pout":         Pout,
        "eta":          eta,
        "I_LF_A":       round(I_LF,    4),
        "I_HF_A":       round(I_HF,    4),
        "I_total_A":    round(I_total,  4),
        "C_holdup_uF":  round(C_holdup_F * 1e6, 1),
        "C_ripple_uF":  round(C_ripple_F * 1e6, 1),
    }


# ── Step 15.5 — voltage rating ────────────────────────────────────────────────

def select_voltage_rating(Vout: float, Vout_max: float) -> dict:
    V_min = max(Vout * 1.12, Vout_max)
    for v in [400, 420, 450, 500]:
        if v >= V_min:
            return {"V_min_V": round(V_min, 1), "V_selected_V": v}
    return {"V_min_V": round(V_min, 1), "V_selected_V": 500}


# ── Step 15.7 + 15.8 — verify designer configuration ─────────────────────────

def verify_configuration(
    config: list[dict],   # [{"value_uF": int, "qty": int, "part_number": str|None}]
    supplier: str,
    series: str,
    voltage_rating: int,
    worst: dict,
    low: dict,
    Vout: float,
    f_line: float,
    Vdc_min: float,
    C_required_uF: float,
) -> dict:
    db       = _load_db()
    ser_db   = db.get(supplier, {}).get(series, {})
    esr_db   = ser_db.get("ESR_mohm", {})
    temp_rating = int(ser_db.get("temp_rating_C") or ser_db.get("op_temp_max_C") or 105)
    T_amb       = 50.0
    is_snap  = any(kw in series.lower() for kw in ["snap","screw","380lx","lx"])
    Rth_ca   = 10.0 if is_snap else 15.0

    C_total_uF  = sum(r["value_uF"] * r["qty"] for r in config)
    total_count = sum(r["qty"] for r in config)
    C_total_F   = C_total_uF * 1e-6

    # Parallel ESR
    esr_inv = 0.0
    for row in config:
        esr_each = _interp_esr(esr_db, int(row["value_uF"]), voltage_rating)
        if esr_each and row["qty"] > 0:
            esr_inv += row["qty"] / esr_each
    ESR_par = (1.0 / esr_inv) if esr_inv > 0 else None

    # Per-cap spec table: ESR each, I_rated from thermal limit
    cap_specs = []
    for row in config:
        v_uF     = int(row["value_uF"])
        esr_each = _interp_esr(esr_db, v_uF, voltage_rating)
        # I_rated from thermal limit: P_max = (T_rating - T_amb) / Rth_ca
        # P_per_cap = I_per_cap² × ESR_each_ohm  → I_rated = sqrt(P_max / ESR_each_ohm)
        esr_ohm  = (esr_each / 1000.0) if esr_each else None
        P_max    = max(0.0, temp_rating - T_amb) / max(Rth_ca, 0.1)
        I_rated  = math.sqrt(P_max / max(esr_ohm or 1e-3, 1e-6)) if esr_ohm else None
        cap_specs.append({
            "value_uF":        v_uF,
            "qty":             int(row["qty"]),
            "voltage_rating_V": voltage_rating,
            "ESR_each_mohm":   round(esr_each, 1) if esr_each else None,
            "I_rated_A":       round(I_rated, 2)  if I_rated  else None,
            "temp_rating_C":   temp_rating,
            "part_number":     row.get("part_number", ""),
        })

    # ESR and I_rated for the overall parallel bank
    if ESR_par and total_count > 0:
        esr_each_equiv = ESR_par * total_count        # each cap's own ESR
        esr_ohm_equiv  = esr_each_equiv / 1000.0
        P_max_eq       = max(0.0, temp_rating - T_amb) / max(Rth_ca, 0.1)
        I_rated_bank   = math.sqrt(P_max_eq / max(esr_ohm_equiv, 1e-6))
    else:
        I_rated_bank = None

    def _perf(op: dict) -> dict:
        P      = op["Pout"]
        eta_op = op["eta"]
        V_rp   = P / (2 * math.pi * f_line * C_total_F * eta_op * Vout) if C_total_F > 0 else 999
        t_hd   = C_total_F * (Vout**2 - Vdc_min**2) / (2 * P) * 1000 if P > 0 else 0
        I_t    = op["I_total_A"]
        # Correct: current splits equally across X parallel caps → I_per_cap = I_total / X
        I_pc   = I_t / max(total_count, 1)
        Vesr   = I_t * (ESR_par / 1000.0) if ESR_par is not None else None
        rip_ok = (I_pc <= I_rated_bank) if I_rated_bank is not None else True
        return {
            "V_ripple_pp_V":       round(V_rp, 3),
            "t_holdup_ms":         round(t_hd, 1),
            "I_rms_per_cap_A":     round(I_pc, 3),
            "I_rms_total_A":       round(I_t,  3),
            "I_rated_per_cap_A":   round(I_rated_bank, 2) if I_rated_bank else None,
            "ripple_current_pass": rip_ok,
            "V_esr_pk_V":          round(Vesr, 3) if Vesr is not None else None,
        }

    margin = (C_total_uF - C_required_uF) / C_required_uF * 100 if C_required_uF > 0 else 0
    wc_perf = _perf(worst)
    ll_perf = _perf(low)

    return {
        "C_total_uF":            round(C_total_uF, 1),
        "total_cap_count":       total_count,
        "valid":                 C_total_uF >= C_required_uF,
        "margin_pct":            round(margin, 1),
        "ESR_parallel_mohm":     round(ESR_par, 1) if ESR_par is not None else None,
        "I_rated_per_cap_A":     round(I_rated_bank, 2) if I_rated_bank else None,
        "ripple_current_pass":   wc_perf["ripple_current_pass"],
        "cap_specs":             cap_specs,
        "supplier":              supplier,
        "series":                series,
        "voltage_rating":        voltage_rating,
        "temp_rating_C":         temp_rating,
        "V_esr_pk_worst_V":      wc_perf.get("V_esr_pk_V"),
        "V_esr_pk_low_V":        ll_perf.get("V_esr_pk_V"),
        "worst_case":            wc_perf,
        "low_line":              ll_perf,
    }


# ── Suggested configurations ──────────────────────────────────────────────────

def suggest_configurations(C_required_uF: float, available_values: list[int]) -> list[dict]:
    avail   = sorted(available_values)
    results = []

    # 1. Fewest caps: single cap >= required, else 2× next lower
    for val in reversed(avail):
        if val >= C_required_uF:
            results.append({"label": "Fewest caps", "rows": [{"value_uF": val, "qty": 1}]})
            break
    else:
        if avail:
            results.append({"label": "Fewest caps",
                            "rows": [{"value_uF": avail[-1], "qty": 2}]})

    # 2. Balanced: 2 or 3 equal caps
    for n in [2, 3]:
        needed = math.ceil(C_required_uF / n)
        for val in avail:
            if val >= needed:
                results.append({"label": f"Balanced ×{n}",
                                "rows": [{"value_uF": val, "qty": n}]})
                break

    # 3. Mixed: largest + fill remainder
    if avail:
        big = avail[-1]
        rem = C_required_uF - big
        if rem <= 0:
            results.append({"label": "Mixed", "rows": [{"value_uF": big, "qty": 1}]})
        else:
            for val in reversed(avail[:-1]):
                n_small = math.ceil(rem / val)
                if n_small <= 4:
                    results.append({"label": "Mixed",
                                    "rows": [{"value_uF": big,   "qty": 1},
                                             {"value_uF": val,   "qty": n_small}]})
                    break

    # Deduplicate by config key
    seen, unique = set(), []
    for c in results:
        key = str(sorted((r["value_uF"], r["qty"]) for r in c["rows"]))
        if key not in seen:
            seen.add(key)
            c["C_total_uF"] = sum(r["value_uF"] * r["qty"] for r in c["rows"])
            unique.append(c)

    return unique[:3]


# ── Enhancement 1 — Custom capacitor datasheet parsing ───────────────────────

def parse_custom_cap_datasheet(pdf_bytes: bytes, part_number: str) -> dict:
    """
    Extract key parameters from an uploaded capacitor datasheet PDF using pdfplumber.
    Returns extracted values with confidence flags.
    Fields that cannot be extracted reliably are set to None so the UI can prompt
    the designer to enter them manually.
    """
    extracted: dict = {
        "capacitance_uF":   None,
        "voltage_rating_V": None,
        "ESR_100Hz_mohm":   None,
        "ESR_120Hz_mohm":   None,
        "ripple_current_A": None,
        "temp_rating_C":    None,
        "life_hours":       None,
    }
    confidence: dict = {k: "manual_required" for k in extracted}

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages[:6])
    except Exception:
        text = ""

    # Capacitance — e.g. "1000 µF", "1000uF", "1000 μF"
    m = re.search(r'(\d+(?:\.\d+)?)\s*[µμu]F', text, re.IGNORECASE)
    if m:
        extracted["capacitance_uF"] = float(m.group(1))
        confidence["capacitance_uF"] = "extracted"

    # Voltage rating — e.g. "450V", "450 Vdc", "450 V (WV)"
    for pat in [
        r'(\d+)\s*V\s*(?:dc|WV|working)',
        r'Rated\s+Voltage\s*[:\-]?\s*(\d+)',
        r'Working\s+Voltage\s*[:\-]?\s*(\d+)',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = int(m.group(1))
            if 50 <= v <= 1000:
                extracted["voltage_rating_V"] = v
                confidence["voltage_rating_V"] = "extracted"
                break

    # ESR at 100Hz and 120Hz
    for freq, key in [(100, "ESR_100Hz_mohm"), (120, "ESR_120Hz_mohm")]:
        for pat in [
            rf'{freq}\s*Hz.*?(\d+(?:\.\d+)?)\s*m[ΩΩ]',
            rf'ESR.*?{freq}.*?(\d+(?:\.\d+)?)\s*m[ΩΩ]',
        ]:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                extracted[key] = float(m.group(1))
                confidence[key] = "extracted"
                break

    # Ripple current
    for pat in [
        r'Ripple\s+Current\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*A',
        r'Rated\s+Ripple\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*A',
        r'Max(?:imum)?\s+Ripple\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*A',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            extracted["ripple_current_A"] = float(m.group(1))
            confidence["ripple_current_A"] = "extracted"
            break

    # Temperature rating
    for pat in [
        r'(\d+)\s*°C.*?(?:max|maximum|operating)',
        r'(?:max|maximum|operating).*?(\d+)\s*°C',
        r'(\d+)\s*[°℃]\s*C\b',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            t = int(m.group(1))
            if 50 <= t <= 175:
                extracted["temp_rating_C"] = t
                confidence["temp_rating_C"] = "extracted"
                break

    # Life hours
    m = re.search(r'([\d,]+)\s*(?:hours?|hrs?)\b', text, re.IGNORECASE)
    if m:
        h = int(m.group(1).replace(",", ""))
        if 500 <= h <= 100000:
            extracted["life_hours"] = h
            confidence["life_hours"] = "extracted"

    can_use = (extracted["capacitance_uF"] is not None
               and extracted["voltage_rating_V"] is not None)

    return {
        "part_number":       part_number,
        "extracted":         extracted,
        "confidence":        confidence,
        "can_use_in_config": can_use,
    }


# ── Enhancement 2 — Thermal table across all 9 operating points ──────────────

_DEFAULT_OPS_9 = [
    (90,  1700, 0.945, 0.9987),
    (110, 1700, 0.955, 0.9986),
    (120, 1700, 0.965, 0.9985),
    (132, 1700, 0.975, 0.9980),
    (180, 3600, 0.965, 0.9889),
    (200, 3600, 0.975, 0.9884),
    (220, 3600, 0.985, 0.9790),
    (230, 3600, 0.988, 0.9789),
    (264, 3600, 0.990, 0.9520),
]


def calculate_thermal_table(
    config: list,
    state: dict,
    supplier: str,
    series: str,
    voltage_rating: int,
) -> dict:
    """
    Step 15 thermal analysis across all 9 operating points.
    For each point: I_cap, I per unit, P_dissipated, ΔT, T_cap, V_ripple, pass/fail.
    """
    intake = state.get("intake", {})
    ap     = intake.get("application", {})
    tsi    = state.get("topology_specific_inputs", {})

    Vout       = float(ap.get("output_bus_voltage_v",      393))
    f_line     = float(ap.get("nominal_line_frequency_hz", 60))
    Vdc_ripple = float(tsi.get("dc_bus_ripple_vpp",        20.0))
    T_amb      = 50.0   # °C ambient

    db       = _load_db()
    ser_db   = db.get(supplier, {}).get(series, {})
    esr_db   = ser_db.get("ESR_mohm", {})
    temp_rating = int(ser_db.get("temp_rating_C") or ser_db.get("op_temp_max_C") or 105)

    # Snap-in / screw → lower Rth; radial aluminium → higher
    is_snap = any(kw in series.lower() for kw in ["snap", "screw", "380lx", "lx"])
    Rth_ca = 10.0 if is_snap else 15.0

    C_total_uF  = sum(r["value_uF"] * r["qty"] for r in config)
    C_total_F   = C_total_uF * 1e-6
    total_count = sum(r["qty"] for r in config)

    # Parallel ESR of the configuration
    esr_inv = 0.0
    for row in config:
        esr_each = _interp_esr(esr_db, int(row["value_uF"]), voltage_rating)
        if esr_each and row["qty"] > 0:
            esr_inv += row["qty"] / esr_each
    ESR_par = (1.0 / esr_inv) if esr_inv > 0 else 500.0  # mΩ fallback

    table = []
    for (Vin_rms, Pout, eta, PF) in _DEFAULT_OPS_9:
        Vin_pk  = math.sqrt(2) * Vin_rms
        I_dc    = Pout / (eta * Vout)
        I_LF    = I_dc / math.sqrt(2)
        denom   = 6 * Vin_pk * 2 * math.pi
        I_HF    = math.sqrt(max(0.0, I_dc**2 * 16 * Vout / denom - I_LF**2)) if denom > 0 else 0.0
        I_total = math.sqrt(I_LF**2 + I_HF**2)

        # Correct: X caps in parallel → each carries I_total / X
        I_per_cap   = I_total / max(total_count, 1)
        P_diss      = I_per_cap**2 * (ESR_par / 1000.0)   # W per cap (ESR in mΩ → Ω)
        dT          = P_diss * Rth_ca
        T_cap       = T_amb + dT
        V_ripple_pp = (Pout / (2 * math.pi * f_line * C_total_F * eta * Vout)
                       if C_total_F > 0 else 999.0)
        # I_rated from thermal limit per cap
        ESR_each_ohm = (ESR_par * total_count) / 1000.0  # individual cap ESR
        P_max_cap    = max(0.0, temp_rating - T_amb) / max(Rth_ca, 0.1)
        I_rated      = math.sqrt(P_max_cap / max(ESR_each_ohm, 1e-6))
        ripple_pass  = I_per_cap <= I_rated

        table.append({
            "Vin_rms":          Vin_rms,
            "Pout_W":           Pout,
            "I_dc_A":           round(I_dc,        3),
            "I_LF_A":           round(I_LF,        3),
            "I_HF_A":           round(I_HF,        3),
            "I_cap_total_A":    round(I_total,      3),
            "I_cap_per_unit_A": round(I_per_cap,   3),
            "I_rated_A":        round(I_rated,      2),
            "P_dissipated_W":   round(P_diss,       3),
            "dT_rise_C":        round(dT,            1),
            "T_cap_C":          round(T_cap,         1),
            "V_ripple_pp_V":    round(V_ripple_pp,   2),
            "ripple_pass":      ripple_pass,
        })

    worst_dT = max(r["dT_rise_C"] for r in table)
    worst_T  = max(r["T_cap_C"]   for r in table)

    return {
        "thermal_table":    table,
        "worst_case_dT_C":  worst_dT,
        "worst_case_T_C":   worst_T,
        "all_ripple_pass":  all(r["ripple_pass"] for r in table),
        "temp_rating_C":    temp_rating,
        "Rth_ca_CW":        Rth_ca,
        "ESR_parallel_mohm": round(ESR_par, 1),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def run_capacitor_design(state: dict) -> dict:
    """Full Step 15.1–15.5 analysis. Returns structured result for endpoint + frontend."""
    intake = state.get("intake", {})
    ap     = intake.get("application", {})
    tsi    = state.get("topology_specific_inputs", {})

    Vout       = float(ap.get("output_bus_voltage_v",      393))
    Pout_high  = float(ap.get("output_power_w_high_line",  3600))
    Pout_low   = float(ap.get("output_power_w_low_line",   1700))
    f_line     = float(ap.get("nominal_line_frequency_hz", 60))
    Vdc_ripple = float(tsi.get("dc_bus_ripple_vpp",        20.0))
    Vdc_min    = float(ap.get("holdup_vmin_v",             290.0))
    t_hold_ms  = float(ap.get("holdup_time_ms",            20.0))
    t_hold_s   = t_hold_ms / 1000.0
    Vout_max   = float(tsi.get("Vout_max_V",               Vout * 1.10))

    worst = calc_operating_point(180, Pout_high, 0.965, Vout, f_line,
                                  Vdc_ripple, Vdc_min, t_hold_s)
    low   = calc_operating_point(90,  Pout_low,  0.945, Vout, f_line,
                                  Vdc_ripple, Vdc_min, t_hold_s)

    # Step 15.4 — C required
    candidates = {
        "C_holdup (worst-case)": worst["C_holdup_uF"],
        "C_ripple (worst-case)": worst["C_ripple_uF"],
        "C_holdup (low-line)":   low["C_holdup_uF"],
        "C_ripple (low-line)":   low["C_ripple_uF"],
    }
    C_required_uF = max(candidates.values())
    governing     = max(candidates, key=candidates.get)

    vr       = select_voltage_rating(Vout, Vout_max)
    db       = _load_db()
    suppliers = list(db.keys())

    # Default series for suggested configs (Panasonic EEUFM)
    def_sup = "Panasonic"
    def_ser = "EEUFM — Standard 105°C"
    def_vrt = str(vr["V_selected_V"])
    ser_db  = db.get(def_sup, {}).get(def_ser, {})
    if def_vrt not in ser_db.get("voltage_ratings", {}):
        def_vrt = "400"
    avail_vals = ser_db.get("voltage_ratings", {}).get(def_vrt, [])
    suggested  = suggest_configurations(C_required_uF, avail_vals)

    return {
        "inputs": {
            "Vout_V":       Vout,      "f_line_Hz":    f_line,
            "Vdc_ripple_V": Vdc_ripple, "Vdc_min_V":   Vdc_min,
            "t_hold_ms":    t_hold_ms,  "Vout_max_V":  Vout_max,
        },
        "worst_case":           worst,
        "low_line":             low,
        "C_required_uF":        round(C_required_uF, 1),
        "governing":            governing,
        "V_rating_min_V":       vr["V_min_V"],
        "V_rating_selected_V":  vr["V_selected_V"],
        "suppliers":            suppliers,
        "suggested_configs":    suggested,
        "default_supplier":     def_sup,
        "default_series":       def_ser,
    }
