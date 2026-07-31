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
    """Return ESR (mΩ) for val_uF at vrating, interpolating if exact not in DB.

    Falls back to the NEAREST available voltage rating before giving up — ESR varies only
    mildly with voltage class, and returning None here used to punt the whole bank to a
    500 mΩ placeholder that collapsed the thermal I_rated and flagged false ripple FAILs."""
    vkey = str(vrating)
    # Exact match
    exact = esr_db.get(str(val_uF), {})
    if vkey in exact:
        return float(exact[vkey])
    # Same capacitance at the nearest available voltage rating
    if exact:
        try:
            vk = min(exact.keys(), key=lambda k: abs(int(k) - int(vrating)))
            return float(exact[vk])
        except (ValueError, TypeError):
            pass

    def _pts_at(vk: str):
        pts = []
        for c_key, v_dict in esr_db.items():
            if vk in v_dict:
                try:
                    pts.append((int(c_key), float(v_dict[vk])))
                except (ValueError, TypeError):
                    pass
        return pts

    # Collect known (C, ESR) pairs at this voltage rating; else at the nearest voltage with data
    pts = _pts_at(vkey)
    if len(pts) < 2:
        volt_keys = sorted({vk for v in esr_db.values() for vk in v
                            if str(vk).isdigit() and len(_pts_at(vk)) >= 2},
                           key=lambda k: abs(int(k) - int(vrating)))
        if not volt_keys:
            return None
        pts = _pts_at(volt_keys[0])
    # Fit K = ESR × C (log-linear relationship)
    K = sum(c * e for c, e in pts) / len(pts)
    return K / val_uF if val_uF > 0 else None


# ── Step 15.2 + 15.3 + 15.6 per operating point ──────────────────────────────

def calc_operating_point(
    Vin_rms: float, Pout: float, eta: float,
    Vout: float, f_line: float,
    Vdc_ripple: float, Vdc_min: float, t_hold_s: float,
    pf: float = 0.99, n_phases: int = 2,
) -> dict:
    """Full Step 15 calc for one operating point."""
    Vin_pk  = math.sqrt(2) * Vin_rms

    # Step 15.6 — RMS currents. SAME model as the DC-bus capacitor SIMULATION page, so both
    # pages judge identical stress:
    #   LF (2·f_line): I_LF = P_out/(√2·V_out)
    #   HF (switching): standard boost-diode RMS identity minus the DC and LF components,
    #   with √N interleave reduction:
    #     I_D,rms² = 8√2·P_in²/(3π·V_ac·PF²·V_out),   I_HF = √(I_D,rms² − I_o² − I_LF²)/√N
    # (The previous 16/(12π) coefficient understated the HF current ≈2× vs this identity,
    #  which made Step 15 pass parts the simulation page then failed on hotspot/margin.)
    Pin     = Pout / max(eta, 1e-9)
    I_o     = Pout / Vout
    I_LF    = Pout / (math.sqrt(2) * Vout)
    ID2     = 8 * math.sqrt(2) * Pin * Pin / (3 * math.pi * Vin_rms * pf * pf * Vout)
    I_HF    = math.sqrt(max(0.0, ID2 - I_o**2 - I_LF**2)) / math.sqrt(max(n_phases, 1))
    I_total = math.hypot(I_LF, I_HF)

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
    cap_ref: dict | None = None,   # selected part record (ratings → vendor-implied ESR(T) model)
    Tamb_C: float = 50.0,
) -> dict:
    db       = _load_db()
    ser_db   = db.get(supplier, {}).get(series, {})
    esr_db   = ser_db.get("ESR_mohm", {})
    temp_rating = int(ser_db.get("temp_rating_C") or ser_db.get("op_temp_max_C") or 105)
    T_amb       = float(Tamb_C or 50.0)
    is_snap  = any(kw in series.lower() for kw in ["snap","screw","380lx","lx"])
    Rth_ca   = 10.0 if is_snap else 15.0
    dT0      = 5.0  if is_snap else 10.0

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

    # ── Vendor-implied ESR(T) model (cap_esr_model): selected part record preferred ────────
    from app.mode_b.cap_esr_model import build_esr_model, solve_core_temp, temp_multiplier, esr_lf_at
    _model_src = dict(cap_ref) if cap_ref else {
        "esr_ohm": ((_interp_esr(esr_db, int(config[0]["value_uF"]), voltage_rating) or 500.0) / 1000.0)
                   if config else 0.5,
        "capacitance_uF": config[0]["value_uF"] if config else 470,
        "op_temp_max_C":  temp_rating,
    }
    esr_m = build_esr_model(_model_src, Rth_ca, dT0)
    _K    = temp_multiplier(esr_m, T_amb, str(_model_src.get("manufacturer", supplier)), series)

    # Per-cap spec table: ESR each + allowed ripple at this ambient
    cap_specs = []
    for row in config:
        v_uF     = int(row["value_uF"])
        esr_each = _interp_esr(esr_db, v_uF, voltage_rating)
        if esr_m.get("I_rated_A"):
            # one basis: K(T_amb) × the datasheet 120 Hz rating (matches table + sim page)
            I_rated = esr_m["I_rated_A"] * _K["K"]
        else:
            # thermal-limit fallback, with the ESR evaluated HOT (at the limit core temp)
            esr_ohm  = (esr_each / 1000.0) if esr_each else None
            P_max    = max(0.0, temp_rating - T_amb) / max(Rth_ca, 0.1)
            I_rated  = math.sqrt(P_max / max(esr_lf_at(esr_m, temp_rating), 1e-6)) if esr_ohm else None
        cap_specs.append({
            "value_uF":        v_uF,
            "qty":             int(row["qty"]),
            "voltage_rating_V": voltage_rating,
            "ESR_each_mohm":   round(esr_each, 1) if esr_each else None,
            "I_rated_A":       round(I_rated, 2)  if I_rated  else None,
            "temp_rating_C":   temp_rating,
            "part_number":     row.get("part_number", ""),
        })

    # Allowed ripple for the bank (per cap) — same basis as cap_specs
    I_rated_bank = cap_specs[0]["I_rated_A"] if cap_specs else None

    def _perf(op: dict) -> dict:
        P      = op["Pout"]
        eta_op = op["eta"]
        V_rp   = P / (2 * math.pi * f_line * C_total_F * eta_op * Vout) if C_total_F > 0 else 999
        t_hd   = C_total_F * (Vout**2 - Vdc_min**2) / (2 * P) * 1000 if P > 0 else 0
        I_t    = op["I_total_A"]
        # Correct: current splits equally across X parallel caps → I_per_cap = I_total / X
        I_pc   = I_t / max(total_count, 1)
        # V_esr with the temperature-corrected ESR at the converged core temperature
        n = max(total_count, 1)
        _s = solve_core_temp(esr_m, float(op.get("I_LF_A", 0)) / n,
                             float(op.get("I_HF_A", 0)) / n, T_amb)
        Vesr = I_t * (_s["esr_lf"] / n)
        from app.mode_b.step15_cap_db import ripple_status as _rip_status
        _status = _rip_status(I_pc, esr_m.get("I_rated_A"), I_rated_bank,
                              _s["T_core"], float(temp_rating), None)
        rip_ok = (_status != 'fail') if I_rated_bank is not None else True
        return {
            "V_ripple_pp_V":       round(V_rp, 3),
            "t_holdup_ms":         round(t_hd, 1),
            "I_rms_per_cap_A":     round(I_pc, 3),
            "I_rms_total_A":       round(I_t,  3),
            "I_rated_per_cap_A":   round(I_rated_bank, 2) if I_rated_bank else None,
            "I_nameplate_A":       esr_m.get("I_rated_A"),
            "ripple_current_pass": rip_ok,
            "ripple_status":       _status,
            "V_esr_pk_V":          round(Vesr, 3) if Vesr is not None else None,
            "ESR_at_op_mohm":      round(_s["esr_lf"] * 1000, 1),
            "T_core_C":            round(_s["T_core"], 1),
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
    # operating ambient from the SPEC (same value the lifetime panel and the sim page use)
    T_amb      = float(intake.get("thermal", {}).get("ambient_temp_c_max", 50.0) or 50.0)

    db       = _load_db()
    ser_db   = db.get(supplier, {}).get(series, {})
    esr_db   = ser_db.get("ESR_mohm", {})
    temp_rating = int(ser_db.get("temp_rating_C") or ser_db.get("op_temp_max_C") or 105)

    # Snap-in / screw → lower Rth; radial aluminium → higher
    is_snap = any(kw in series.lower() for kw in ["snap", "screw", "380lx", "lx"])
    Rth_ca = 10.0 if is_snap else 15.0
    dT0    = 5.0  if is_snap else 10.0

    C_total_uF  = sum(r["value_uF"] * r["qty"] for r in config)
    C_total_F   = C_total_uF * 1e-6
    total_count = sum(r["qty"] for r in config)

    # Parallel ESR of the configuration (datasheet 20 °C basis, for display/V_esr reference)
    esr_inv = 0.0
    for row in config:
        esr_each = _interp_esr(esr_db, int(row["value_uF"]), voltage_rating)
        if esr_each and row["qty"] > 0:
            esr_inv += row["qty"] / esr_each
    ESR_par = (1.0 / esr_inv) if esr_inv > 0 else 500.0  # mΩ fallback

    # ── Vendor-implied ESR(T) model (cap_esr_model) ──────────────────────────
    # Prefer the part's own CSV record (carries the rated ripple currents that set the hot
    # anchor); fall back to the series-interpolated 20 °C ESR with no hot anchor (esr20_only —
    # exactly the previous behaviour).
    from app.mode_b.cap_esr_model import build_esr_model, solve_core_temp, temp_multiplier
    _pn  = next((str(r.get("part_number") or "") for r in config if r.get("part_number")), "")
    _rec = None
    if _pn:
        try:
            from app.mode_b.step15_cap_db import _load as _load_csv
            _rec = next((x for x in _load_csv()
                         if str(x.get("part_number", "")).lower() == _pn.lower()), None)
        except Exception:
            _rec = None
    if _rec is None:
        _rec = {"esr_ohm": (ESR_par * total_count) / 1000.0,
                "capacitance_uF": config[0]["value_uF"] if config else 470,
                "op_temp_max_C": temp_rating}
    else:
        # the part record knows its true package — more reliable than the series-NAME heuristic
        # (e.g. series "HXK" doesn't contain "snap" but the part is a snap-in can)
        _pkg = (str(_rec.get("package") or "") + " " + str(_rec.get("mounting") or "")).lower()
        if _pkg.strip():
            is_snap = any(k in _pkg for k in ("snap", "screw"))
            Rth_ca  = 10.0 if is_snap else 15.0
            dT0     = 5.0  if is_snap else 10.0
    esr_m = build_esr_model(_rec, Rth_ca, dT0)
    _K    = temp_multiplier(esr_m, T_amb, _rec.get("manufacturer", supplier), series)

    n_phases = int(state.get("selected_channels") or 2)
    # Operating grid from the DESIGNER'S intake — NOT the old hardcoded _DEFAULT_OPS_9
    # (fixed 90-264 V / 1700-3600 W / eta / PF). Same canonical_ops_table the inductor
    # chapters use, so the capacitor section shares one operating-point definition
    # (one-engine) and reflects the designer's actual specs.
    _vin_lo = float(ap.get("vin_rms_min", 90) or 90)
    _vin_hi = float(ap.get("vin_rms_max", 264) or 264)
    _pout_lo = float(ap.get("output_power_w_low_line", 1700) or 1700)
    _pout_hi = float(ap.get("output_power_w_high_line", 3600) or 3600)
    _eta_t = float(ap.get("efficiency_target_percent", 0) or 0)
    _eta_t = (_eta_t / 100.0) if _eta_t else None
    try:
        from app.mode_b.calculations import canonical_ops_table
        _ops9 = [(float(r[0]), float(r[1]), float(r[2]), float(r[3]))
                 for r in canonical_ops_table(_vin_lo, _vin_hi, _pout_lo, _pout_hi, _eta_t)]
    except Exception:
        _ops9 = _DEFAULT_OPS_9
    table = []
    for (Vin_rms, Pout, eta, PF) in _ops9:
        # SAME HF ripple-current model as calc_operating_point / the simulation page
        Pin     = Pout / max(eta, 1e-9)
        I_o     = Pout / Vout
        I_dc    = I_o                       # output DC current (basis of the decomposition)
        I_LF    = Pout / (math.sqrt(2) * Vout)
        ID2     = 8 * math.sqrt(2) * Pin * Pin / (3 * math.pi * Vin_rms * PF * PF * Vout)
        I_HF    = math.sqrt(max(0.0, ID2 - I_o**2 - I_LF**2)) / math.sqrt(max(n_phases, 1))
        I_total = math.hypot(I_LF, I_HF)

        # X caps in parallel → each carries I/X; per-cap dissipation uses the cap's OWN
        # (temperature-corrected) ESR at its converged core temperature — this also fixes the
        # old bug that multiplied the per-cap current by the bank-PARALLEL ESR (which
        # under-counted per-cap loss by the parallel count).
        n = max(total_count, 1)
        I_per_cap = I_total / n
        _s   = solve_core_temp(esr_m, I_LF / n, I_HF / n, T_amb)
        P_diss = _s["P_W"]; dT = _s["dT"]; T_cap = _s["T_core"]
        V_ripple_pp = (Pout / (2 * math.pi * f_line * C_total_F * eta * Vout)
                       if C_total_F > 0 else 999.0)
        # Allowed ripple at this ambient: K(T_amb) × the datasheet rating (one basis with the
        # part table and the simulation page). Thermal-limit fallback when no rating exists.
        if esr_m.get("I_rated_A"):
            I_rated = esr_m["I_rated_A"] * _K["K"]
        else:
            from app.mode_b.cap_esr_model import esr_lf_at
            P_max_cap = max(0.0, temp_rating - T_amb) / max(Rth_ca, 0.1)
            I_rated   = math.sqrt(P_max_cap / max(esr_lf_at(esr_m, temp_rating), 1e-6))
        # three-tier verdict (pass / pass_derated / fail); lifetime is gated by §5.4
        from app.mode_b.step15_cap_db import ripple_status as _rip_status
        r_status    = _rip_status(I_per_cap, esr_m.get("I_rated_A"), I_rated,
                                  T_cap, float(temp_rating), None)
        ripple_pass = (r_status != 'fail')

        table.append({
            "Vin_rms":          Vin_rms,
            "Pout_W":           Pout,
            "PF":               PF,
            "I_dc_A":           round(I_dc,        3),
            "I_LF_A":           round(I_LF,        3),
            "I_HF_A":           round(I_HF,        3),
            "I_cap_total_A":    round(I_total,      3),
            "I_cap_per_unit_A": round(I_per_cap,   3),
            "I_rated_A":        round(I_rated,      2),
            "P_dissipated_W":   round(P_diss,       3),
            "dT_rise_C":        round(dT,            1),
            "T_cap_C":          round(T_cap,         1),
            "ESR_lf_mohm":      round(_s["esr_lf"] * 1000, 1),
            "ESR_hf_mohm":      round(_s["esr_hf"] * 1000, 1),
            "V_ripple_pp_V":    round(V_ripple_pp,   2),
            "ripple_pass":      ripple_pass,
            "ripple_status":    r_status,       # 'pass' | 'pass_derated' | 'fail'
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
        "n_phases":         n_phases,
        "T_amb_C":          T_amb,
        # vendor-implied ESR(T) model summary (documented in the report's capacitor chapter)
        "esr_model": {
            "source":       esr_m["source"],
            "esr20_mohm":   round(esr_m["esr20"] * 1000, 1),
            "esr_hot_mohm": round(esr_m["esr_hot"] * 1000, 1),
            "T_hot_C":      round(esr_m["T_hot"], 0),
            "kf":           round(esr_m["kf"], 2),
            "K_temp":       round(_K["K"], 2),
            "K_source":     _K["source"],
            "I_rated_A":    esr_m.get("I_rated_A"),
        },
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
    # canonical intake key is hold_up_time_ms (intake/schema.py); the old holdup_time_ms spelling
    # never matched, silently forcing the 20 ms default over the designer's spec-page value.
    t_hold_ms  = float(ap.get("hold_up_time_ms", ap.get("holdup_time_ms", 20.0)))
    t_hold_s   = t_hold_ms / 1000.0
    Vout_max   = float(tsi.get("Vout_max_V",               Vout * 1.10))

    nch = int(state.get("selected_channels") or 2)
    # η/PF for the two sizing corners from the designer-anchored canonical ladder — NOT
    # the old 0.965/0.9889 and 0.945/0.9987 literals. Low corner = designer's vin_min; worst
    # corner = 180 V (high-line band minimum, the worst for DC-bus ripple per the C81 model).
    _vin_lo = float(ap.get("vin_rms_min", 90) or 90)
    _vin_hi = float(ap.get("vin_rms_max", 264) or 264)
    _eta_t  = float(ap.get("efficiency_target_percent", 0) or 0)
    _eta_t  = (_eta_t / 100.0) if _eta_t else None
    _v_worst, _eta_w, _pf_w = 180.0, 0.965, 0.9889
    _eta_l, _pf_l = 0.945, 0.9987
    try:
        from app.mode_b.calculations import canonical_ops_table
        _ops = canonical_ops_table(_vin_lo, _vin_hi, Pout_low, Pout_high, _eta_t)
        _lo_r = _ops[0]                                                   # vin_min / low-line
        _hi_r = next((r for r in _ops if float(r[0]) >= 180.0), _ops[4])  # 180 V / high-line
        _v_worst, _eta_w, _pf_w = float(_hi_r[0]), float(_hi_r[2]), float(_hi_r[3])
        _eta_l, _pf_l = float(_lo_r[2]), float(_lo_r[3])
    except Exception:
        pass
    worst = calc_operating_point(_v_worst, Pout_high, _eta_w, Vout, f_line,
                                  Vdc_ripple, Vdc_min, t_hold_s, pf=_pf_w, n_phases=nch)
    low   = calc_operating_point(_vin_lo,  Pout_low,  _eta_l, Vout, f_line,
                                  Vdc_ripple, Vdc_min, t_hold_s, pf=_pf_l, n_phases=nch)

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
            "vin_rms_min":  float(ap.get("vin_rms_min", 90) or 90),
            "vin_rms_max":  float(ap.get("vin_rms_max", 264) or 264),
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


# ══════════════════════════════════════════════════════════════════════════════
#  Capacitor bank loss — SINGLE SOURCE OF TRUTH
# ══════════════════════════════════════════════════════════════════════════════
def bank_loss_table(step15_result: dict, state: dict) -> dict | None:
    """Per-operating-point DC-bus capacitor bank loss, from the ONE engine that owns it.

    Chapter 5 (Table 5.3.1) and the Chapter-7 Section 7.8b system loss budget must quote the same
    capacitor loss. Both now come from here, which wraps `calculate_thermal_table` — the model that
    solves the vendor-implied ESR at each point's actual core temperature (`cap_esr_model`).

    Do NOT re-derive this as I_rms^2 * ESR from a nominal ESR elsewhere: the series-level ESR table and
    the control-loop plant ESR (`step16_params.ESR_mOhm`, which sizes the loop zero) are different
    quantities and give answers that differ by several times.

    Returns {"by_vac": {Vac: P_bank_W}, "rows": [...], "worst": {...}, "n_cap": N} or None when the
    bank is not resolvable (no selected part) — None means DATA MISSING, never a substituted value.
    """
    sel = (step15_result or {}).get("selected_cap") or {}
    if not sel:
        return None
    try:
        n_cap = int(float(sel.get("qty", 1) or 1))
        cfg = [{"value_uF": int(float(sel.get("value_uF", 0) or 0)), "qty": n_cap,
                "part_number": sel.get("part_number", "")}]
        th = calculate_thermal_table(config=cfg, state=state or {},
                                     supplier=sel.get("supplier", "—"),
                                     series=sel.get("series", "—"),
                                     voltage_rating=int(float(sel.get("voltage_rating_V", 0) or 0)))
    except Exception:
        return None
    rows = (th or {}).get("thermal_table") or []
    if not rows:
        return None
    out_rows, by_vac, worst = [], {}, None
    for r in rows:
        p_cap = float(r.get("P_dissipated_W", 0.0))
        p_bank = n_cap * p_cap
        rec = {"Vin_rms": float(r["Vin_rms"]), "Pout_W": float(r["Pout_W"]),
               "I_cap_total_A": float(r["I_cap_total_A"]),
               "I_cap_per_unit_A": float(r["I_cap_per_unit_A"]),
               "T_cap_C": float(r.get("T_cap_C", 0.0)),
               "P_cap_W": p_cap, "P_bank_W": p_bank,
               # ESR the model actually used at this point, so the report can show its basis
               "ESR_per_cap_mohm": (1e3 * p_cap / (float(r["I_cap_per_unit_A"]) ** 2)
                                    if r.get("I_cap_per_unit_A") else None)}
        out_rows.append(rec)
        by_vac[round(rec["Vin_rms"])] = p_bank
        if worst is None or p_bank > worst["P_bank_W"]:
            worst = rec
    return {"by_vac": by_vac, "rows": out_rows, "worst": worst, "n_cap": n_cap}
