"""
step15_cap_db.py
HV Aluminium Electrolytic Capacitor database access.
Provides filter options, filtered capacitance lists, and full cap tables
with computed ESR and Irms for the Step 15 designer workflow.
"""
from __future__ import annotations
import csv, math, os
from typing import Optional

_HERE    = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, 'data', 'hv_cap_database.csv')

HOURS_PER_YEAR = 8760.0
LIFE_TARGET_YR = 15.0    # design minimum


def calculate_lifetime(
    cap: dict,
    qty: int,
    I_LF_total: float,   # total bank LF RMS current (worst-case, A)
    I_HF_total: float,   # total bank HF RMS current (worst-case, A)
    Tamb: float,         # capacitor ambient temperature (°C)
    Vout: float,         # operating DC bus voltage (V)
) -> dict:
    """
    Compute capacitor lifetime using three independent methods as described
    in Output_Capacitor_Calculation.docx (Steps 15.10–15.15).

    Returns per-method results and governing (minimum) lifetime.
    """
    qty     = max(int(qty), 1)
    I_LF    = I_LF_total / qty
    I_HF    = I_HF_total / qty

    # ── Cap parameters ──────────────────────────────────────────────────────
    Lo      = float(cap.get('lifetime_hours') or 2000)
    Tmax    = float(cap.get('op_temp_max_C')  or 105)
    Vo      = float(cap.get('voltage_V')      or 450)
    C_uF    = float(cap.get('capacitance_uF') or 470)
    C_F     = C_uF * 1e-6
    tan_d   = float(cap.get('tan_delta')      or 0.15)
    esr_db  = float(cap.get('esr_ohm') or 0.0)

    pkg     = str(cap.get('package') or '').lower()
    is_snap = 'snap' in pkg or 'screw' in pkg
    Rth     = 10.0 if is_snap else 15.0    # °C/W
    k_prod  = 0.17 if is_snap else 0.25    # product-type coefficient
    delta_To= 5.0  if is_snap else 10.0    # rated core rise (°C)

    Io_lf   = float(cap.get('ripple_120hz_A') or 1.0)
    Io_hf   = float(cap.get('ripple_hf_A') or Io_lf * 1.94)
    kf_lf   = 1.00
    kf_hf   = (Io_hf / Io_lf) if Io_lf > 0 else 1.94
    kv      = 3.37   # size constant (60 mm can length, per document)

    def _yr(h): return round(h / HOURS_PER_YEAR, 1)

    # ── Method 1 (INTERNAL bound): Arrhenius from vendor-implied ESR(T) ───
    # Uses the temperature-corrected ESR at the converged core temperature (cap_esr_model),
    # replacing the old cold-max ESR that double-counted the rated-ripple self-heating.
    from app.mode_b.cap_esr_model import build_esr_model, solve_core_temp
    _m1s    = solve_core_temp(build_esr_model(cap, Rth, delta_To), I_LF, I_HF, Tamb)
    esr_lf1 = _m1s['esr_lf']
    esr_hf1 = _m1s['esr_hf']
    P1      = _m1s['P_W']
    dT1     = _m1s['dT']
    Tc1     = _m1s['T_core']
    fT1     = 2 ** ((Tmax - Tc1) / 10)
    fV1     = (Vo / Vout) ** 3
    L1_h    = Lo * fT1 * fV1
    m1 = {
        'name': 'Method 1 — Datasheet ESR (Arrhenius)',
        'esr_lf_ohm': round(esr_lf1, 4), 'esr_hf_ohm': round(esr_hf1, 4),
        'P_W': round(P1, 3), 'dT_C': round(dT1, 1), 'T_core_C': round(Tc1, 1),
        'temp_factor': round(fT1, 2), 'volt_factor': round(fV1, 3),
        'life_hours': round(L1_h), 'life_years': _yr(L1_h),
    }

    # ── Method 2: Arrhenius from tan-δ derived ESR (worst-case) ──────────
    esr_lf2 = tan_d / (2 * math.pi * 120 * C_F)
    esr_hf2 = 0.30 * esr_lf2
    P2      = I_LF**2 * esr_lf2 + I_HF**2 * esr_hf2
    dT2     = P2 * Rth
    Tc2     = Tamb + dT2
    fT2     = 2 ** ((Tmax - Tc2) / 10)
    fV2     = (Vo / Vout) ** 3
    L2_h    = Lo * fT2 * fV2
    m2 = {
        'name': 'Method 2 — tan-δ ESR (Arrhenius, worst-case)',
        'esr_lf_ohm': round(esr_lf2, 4), 'esr_hf_ohm': round(esr_hf2, 4),
        'P_W': round(P2, 3), 'dT_C': round(dT2, 1), 'T_core_C': round(Tc2, 1),
        'temp_factor': round(fT2, 2), 'volt_factor': round(fV2, 3),
        'life_hours': round(L2_h), 'life_years': _yr(L2_h),
    }

    # ── Method 3: Manufacturer model (Steps 15.12–15.15) ─────────────────
    I_eq    = math.sqrt((I_LF / kf_lf)**2 + (I_HF / kf_hf)**2)
    dTj     = delta_To * (I_eq / Io_lf)**2
    Tc3     = Tamb + dTj
    fT3     = 2 ** ((Tmax - Tamb) / 10)   # uses Tamb, not T_core
    d_To    = 10 - k_prod * delta_To
    d_Tj    = 10 - k_prod * dTj
    fI      = 2 ** (delta_To / d_To - dTj / d_Tj) if d_To > 0 and d_Tj > 0 else 1.0
    fV3_raw = 5 * (kv - 1) * (1 - Vout / Vo) + 1
    fV3     = min(kv, fV3_raw)
    L3_h    = Lo * fT3 * fI * fV3
    # Cap reported value at 200 yr — physically impossible, show capped
    L3_rep  = min(L3_h / HOURS_PER_YEAR, 200.0)
    m3 = {
        'name': 'Method 3 — Manufacturer Model',
        'I_eq_A': round(I_eq, 4), 'dTj_C': round(dTj, 2), 'T_core_C': round(Tc3, 2),
        'f_T': round(fT3, 2), 'f_I': round(fI, 4), 'f_V': round(fV3, 4),
        'life_hours': round(min(L3_h, 200 * HOURS_PER_YEAR)),
        'life_years': round(L3_rep, 1),
        'life_hours_uncapped': round(L3_h),
        'life_years_uncapped': round(L3_h / HOURS_PER_YEAR, 1),
    }

    # ── Life Time Period — the pass criterion ─────────────────────────────
    # Method 3 (the manufacturer's own published model) is the ONLY passing criterion: it is the
    # basis on which the endurance rating L0 and the ripple/temperature multipliers are defined,
    # and it correctly credits the rated-ripple self-heating baked into L0 (f_I term). Methods 1
    # and 2 remain in the payload as INTERNAL conservative bounds (max-tan-δ ESR + they charge the
    # full self-heat against L0 twice) — they are not shown in the GUI or the documentation and
    # do not gate the design. Designer decision 2026-07-14.
    m3['name'] = 'Life Time Period (manufacturer model)'
    life_yr = m3['life_years']            # display-capped at 200 yr above

    return {
        'method1': m1, 'method2': m2, 'method3': m3,   # m1/m2 = internal bounds only
        'life_years': round(life_yr, 1),               # "Life Time Period"
        'min_life_years': round(life_yr, 1),           # legacy alias (sim anchor, verdicts)
        'min_life_hours': round(life_yr * HOURS_PER_YEAR),
        'pass_15yr': life_yr >= LIFE_TARGET_YR,
        'governing_method': 'Life Time Period',
        'Tamb_C': Tamb, 'Vout_V': Vout,
        'qty': qty,
        'I_LF_per_cap_A': round(I_LF, 4),
        'I_HF_per_cap_A': round(I_HF, 4),
    }

_DB: list | None = None

def characterize_temperature_sweep(
    cap: dict,            # part record (DB row or selected_cap-like dict)
    qty: int,
    I_LF_bank: float,     # bank LF (120 Hz) RMS current [A]
    I_HF_bank: float,     # bank HF (switching) RMS current [A]
    Vout: float,
    T_op: float = 50.0,   # designer operating ambient
) -> dict:
    """Temperature characterization of the SELECTED capacitor (designer request 2026-07-16):
    for a set of ambient temperatures compute 1) ESR (no-load at T_amb AND at the converged
    core), 2) the allowed 120 Hz ripple I_allow = K(T_amb)·I_rated (clamped, with the raw
    thermal multiplier shown alongside), 3) the Life Time Period, 4) T_core — so the designer
    sees the whole capability curve, with each number labelled at its own temperature basis.

    Anchor rows: 0/20/25 °C (cold/room), the operating ambient, 85 °C, and the rated
    temperature (validation row — I_allow reduces to the nameplate there and ESR to the hot
    anchor). Everything derives from the part's own record via cap_esr_model — nothing is
    part- or vendor-specific."""
    from app.mode_b.cap_esr_model import (build_esr_model, esr_lf_at, solve_core_temp,
                                          temp_multiplier)
    qty  = max(int(qty), 1)
    pkg  = (str(cap.get('package') or '') + ' ' + str(cap.get('mounting') or '')
            + ' ' + str(cap.get('series') or '')).lower()
    snap = any(k in pkg for k in ('snap', 'screw'))
    Rth, dT0 = (10.0, 5.0) if snap else (15.0, 10.0)
    m    = build_esr_model(cap, Rth, dT0)
    t_rated = float(cap.get('op_temp_max_C') or cap.get('temp_rating_C') or 105)
    ambients = sorted({0.0, 20.0, 25.0, float(T_op), 85.0, t_rated})
    ilf, ihf = I_LF_bank / qty, I_HF_bank / qty

    rows = []
    for T in ambients:
        s = solve_core_temp(m, ilf, ihf, T)
        K = temp_multiplier(m, T, str(cap.get('manufacturer', '')), str(cap.get('series', '')))
        # raw (un-clamped) thermal multiplier — the pure core-limit capability
        dTa   = max(m['tmax'] + m['dT0'] - T, 0.0)
        K_raw = (math.sqrt(dTa / (m['Rth'] * m['esr_hot'])) / m['I_rated_A']
                 if (m.get('I_rated_A') and dTa > 0) else None)
        lt = calculate_lifetime(cap, qty, I_LF_bank, I_HF_bank, T, Vout)
        rows.append({
            'T_amb_C':          T,
            'esr_at_amb_mohm':  round(esr_lf_at(m, T) * 1000, 1),
            'esr_at_core_mohm': round(s['esr_lf'] * 1000, 1),
            'T_core_C':         round(s['T_core'], 1),
            'K':                round(K['K'], 2),
            'K_source':         K['source'],
            'K_raw':            round(K_raw, 2) if K_raw is not None else None,
            'K_clamped':        bool(K_raw is not None and K['source'] == 'model_implied'
                                     and K_raw > K['K'] + 1e-9),
            'I_allow_A':        round(K['K'] * m['I_rated_A'], 2) if m.get('I_rated_A') else None,
            'life_years':       lt['life_years'],
            'life_pass':        lt['pass_15yr'],
            'is_operating':     abs(T - float(T_op)) < 1e-9,
            'is_rated':         abs(T - t_rated) < 1e-9,
        })
    return {
        'rows':            rows,
        'model':           {'esr20_mohm': round(m['esr20'] * 1000, 1),
                            'esr_hot_mohm': round(m['esr_hot'] * 1000, 1),
                            'T_hot_C': round(m['T_hot'], 0), 'kf': round(m['kf'], 2),
                            'source': m['source'], 'I_rated_A': m.get('I_rated_A'),
                            'Rth_CW': Rth, 'dT0_C': dT0},
        'I_req_per_cap_A': round(math.hypot(I_LF_bank, I_HF_bank) / qty, 3),
        'T_op_C':          float(T_op),
        'T_rated_C':       t_rated,
    }


def ripple_status(I_per_cap: float, I_rated: float | None, I_allow: float | None,
                  T_core: float | None = None, temp_rating: float | None = None,
                  life_pass: bool | None = None) -> str:
    """Three-tier ripple verdict (designer decision 2026-07-16):
      'pass'         — within the NAMEPLATE rating (no temperature credit needed)
      'pass_derated' — above nameplate but within K(T_amb)·rating, core temp within the
                       rating, and (when known) the Life Time Period target met — the
                       vendor-sanctioned temperature allowance, shown as an amber warning
                       rather than a failure
      'fail'         — beyond the allowance, or core/lifetime limit violated"""
    if I_rated is None or I_allow is None:
        return 'pass'                      # no rating data → no basis to fail on
    if T_core is not None and temp_rating is not None and T_core > temp_rating:
        return 'fail'
    if life_pass is False:
        return 'fail'
    if I_per_cap <= I_rated:
        return 'pass'
    if I_per_cap <= I_allow:
        return 'pass_derated'
    return 'fail'


def _load() -> list:
    """Load HV capacitor database from CSV (flat tabular, human-editable in Excel)."""
    global _DB
    if _DB is None:
        records = []
        with open(_DB_PATH, encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                # Convert numeric fields from string to float/int
                for field in ('capacitance_uF','esr_ohm','tan_delta',
                              'lifetime_hours','lifetime_temp_C',
                              'op_temp_min_C','op_temp_max_C',
                              'ripple_120hz_A','ripple_hf_A',
                              'lead_spacing_mm','diameter_mm','height_mm'):
                    v = row.get(field, '')
                    row[field] = float(v) if v and v.lower() not in ('none','') else None
                v = row.get('voltage_V', '')
                row['voltage_V'] = int(float(v)) if v and v.lower() not in ('none','') else None
                for bf in ('aec_q200', 'rohs'):
                    row[bf] = str(row.get(bf,'')).lower() in ('true','1','yes')
                records.append(row)
        _DB = records
    return _DB


# ── Filter options (distinct values for each criterion) ──────────────────────

def get_filter_options() -> dict:
    db = _load()
    voltages   = sorted({r['voltage_V']      for r in db if r['voltage_V']})
    op_temps   = sorted({r['op_temp_raw']     for r in db if r['op_temp_raw']},
                        key=lambda s: (0 if s.startswith('-40') else
                                       1 if s.startswith('-25') else
                                       2 if s.startswith('-55') else 3))
    lifetimes  = sorted({r['lifetime_raw']    for r in db if r['lifetime_raw']},
                        key=lambda s: (
                            int(s.split()[0].replace(',', ''))
                            if s.split() and s.split()[0].replace(',', '').isdigit()
                            else 0))
    tolerances = sorted({r['tolerance']       for r in db if r['tolerance']})
    lead_sps   = sorted({r['lead_spacing_mm'] for r in db if r['lead_spacing_mm']})
    diameters  = sorted({r['diameter_mm']     for r in db if r['diameter_mm']})
    heights    = sorted({r['height_mm']       for r in db if r['height_mm']})
    mfrs       = sorted({r['manufacturer']    for r in db if r['manufacturer']})

    return {
        'voltages':       voltages,
        'op_temps':       op_temps,
        'lifetimes':      lifetimes,
        'tolerances':     tolerances,
        'lead_spacings':  lead_sps,
        'diameters':      diameters,
        'heights':        heights,
        'manufacturers':  mfrs,
    }


# ── Filter caps and return available capacitance values ───────────────────────

def filter_capacitances(
    voltage_V:        Optional[int]   = None,
    op_temp:          Optional[str]   = None,
    lifetime:         Optional[str]   = None,
    tolerance:        Optional[str]   = None,
    lead_spacing_mm:  Optional[float] = None,
    height_max_mm:    Optional[float] = None,
    diameter_max_mm:  Optional[float] = None,
) -> list[float]:
    db = _load()
    filtered = db
    if voltage_V:
        filtered = [r for r in filtered if r['voltage_V'] == int(voltage_V)]
    if op_temp:
        filtered = [r for r in filtered if r['op_temp_raw'] == op_temp]
    if lifetime:
        filtered = [r for r in filtered if r['lifetime_raw'] == lifetime]
    if tolerance:
        filtered = [r for r in filtered if r['tolerance'] == tolerance]
    if lead_spacing_mm is not None:
        filtered = [r for r in filtered if r['lead_spacing_mm'] == float(lead_spacing_mm)]
    if height_max_mm is not None:
        filtered = [r for r in filtered if r['height_mm'] and r['height_mm'] <= float(height_max_mm)]
    if diameter_max_mm is not None:
        filtered = [r for r in filtered if r['diameter_mm'] and r['diameter_mm'] <= float(diameter_max_mm)]

    caps = sorted({r['capacitance_uF'] for r in filtered})
    return caps


# ── Build cap table: all matching parts for a capacitance + filters ───────────

def get_cap_table(
    capacitance_uF:   float,
    n_parallel:       int,
    I_total_A:        float,    # total RMS current through the cap bank
    Vout:             float,
    f_line:           float,
    voltage_V:        Optional[int]   = None,
    op_temp:          Optional[str]   = None,
    lifetime:         Optional[str]   = None,
    tolerance:        Optional[str]   = None,
    lead_spacing_mm:  Optional[float] = None,
    height_max_mm:    Optional[float] = None,
    diameter_max_mm:  Optional[float] = None,
    C_required_uF:    float           = 0.0,
    Tamb_C:           float           = 50.0,   # designer operating ambient → ESR(T), K(T)
    I_LF_A:           Optional[float] = None,   # bank LF (120 Hz) RMS — for the core-temp solve
    I_HF_A:           Optional[float] = None,   # bank HF (switching) RMS
) -> list[dict]:
    """
    Return a table of all caps matching capacitance + filter criteria.
    For each cap compute:
      - ESR (from database)
      - I_rms per cap = I_total / sqrt(n_parallel)  [thermal model]
      - I_rms per cap = I_total / n_parallel         [current split]
      - Ripple current headroom vs rated
      - Pass/fail
    """
    db = _load()
    matched = [r for r in db if abs(r['capacitance_uF'] - float(capacitance_uF)) < 0.5]

    # Apply same filters
    if voltage_V:
        matched = [r for r in matched if r['voltage_V'] == int(voltage_V)]
    if op_temp:
        matched = [r for r in matched if r['op_temp_raw'] == op_temp]
    if lifetime:
        matched = [r for r in matched if r['lifetime_raw'] == lifetime]
    if tolerance:
        matched = [r for r in matched if r['tolerance'] == tolerance]
    if lead_spacing_mm is not None:
        matched = [r for r in matched if r['lead_spacing_mm'] == float(lead_spacing_mm)]
    if height_max_mm is not None:
        matched = [r for r in matched if r['height_mm'] and r['height_mm'] <= float(height_max_mm)]
    if diameter_max_mm is not None:
        matched = [r for r in matched if r['diameter_mm'] and r['diameter_mm'] <= float(diameter_max_mm)]

    if not matched:
        return []

    # Current per cap (parallel split)
    n = max(int(n_parallel), 1)
    I_per_cap = I_total_A / n
    # LF/HF split for the ESR(T) core-temp solve; fall back to a consistent decomposition of
    # the total when the caller doesn't supply the bank components.
    _ilf = float(I_LF_A) if I_LF_A else I_total_A * 0.65
    _ihf = float(I_HF_A) if I_HF_A else math.sqrt(max(I_total_A**2 - _ilf**2, 0.0))

    from app.mode_b.cap_esr_model import build_esr_model, solve_core_temp, temp_multiplier

    # Parallel ESR
    rows = []
    for r in matched:
        esr_each  = r['esr_ohm'] or 0.0

        # Case-to-ambient thermal resistance by package type (same model as
        # verify_configuration): snap-in / screw cans run cooler than radial leaded.
        pkg_txt = (str(r.get('package') or '') + ' ' + str(r.get('mounting') or '')).lower()
        is_snap = any(k in pkg_txt for k in ('snap', 'screw'))
        Rth_ca  = 10.0 if is_snap else 15.0
        dT0     = 5.0  if is_snap else 10.0

        # Vendor-implied ESR(T): per-cap loss and core temperature at the designer's ambient,
        # with the electrolyte NTC captured between the part's own cold/hot anchors.
        _m  = build_esr_model(r, Rth_ca, dT0)
        _s  = solve_core_temp(_m, _ilf / n, _ihf / n, Tamb_C)
        esr_op    = _s['esr_lf']                          # corrected LF ESR at T_core
        esr_par   = (esr_op / n) if n > 0 else esr_op
        V_esr_pk  = round(I_total_A * esr_par, 3)

        # Allowed ripple at this ambient: K(T_amb) × datasheet rating (one basis everywhere)
        rated_rip = r.get('ripple_120hz_A')
        _K   = temp_multiplier(_m, Tamb_C, r.get('manufacturer', ''), r.get('series', ''))
        I_allow = round(rated_rip * _K['K'], 2) if rated_rip else None
        # three-tier verdict: pass (within nameplate) / pass_derated (within temperature
        # allowance + lifetime met) / fail
        _lt_ok = None
        if rated_rip:
            try:
                _lt_ok = calculate_lifetime(r, n, _ilf, _ihf, Tamb_C, Vout)['pass_15yr']
            except Exception:
                _lt_ok = None
        status = ripple_status(I_per_cap, rated_rip, I_allow, _s['T_core'],
                               float(r.get('op_temp_max_C') or 105), _lt_ok)
        rip_pass  = (status != 'fail') if I_allow else None
        headroom  = round((I_allow - I_per_cap) / I_allow * 100, 1) if I_allow else None

        rows.append({
            'manufacturer':    r['manufacturer'],
            'series':          r['series'],
            'part_number':     r['part_number'],
            'digikey_pn':      r['digikey_pn'],
            'capacitance_uF':  r['capacitance_uF'],
            'voltage_V':       r['voltage_V'],
            'tolerance':       r['tolerance'],
            'esr_each_ohm':    round(esr_each, 4),
            'esr_parallel_mohm': round(esr_par * 1000, 2),
            # vendor-implied ESR(T): datasheet 20 °C value vs the corrected value at the
            # converged core temperature for this ambient (see cap_esr_model)
            'esr_at_op_mohm':  round(esr_op * 1000, 1),
            'esr_hf_at_op_mohm': round(_s['esr_hf'] * 1000, 1),
            'T_core_C':        round(_s['T_core'], 1),
            'esr_source':      _s['source'],
            'K_temp':          round(_K['K'], 2),
            'K_temp_source':   _K['source'],
            'I_allow_A':       I_allow,
            'V_esr_pk_V':      V_esr_pk,
            'I_rms_per_cap_A': round(I_per_cap, 3),
            'I_rated_120hz_A': rated_rip,
            'ripple_hf_A':     r.get('ripple_hf_A'),       # rated ripple at HF (for freq multiplier)
            'ripple_pass':     rip_pass,
            'ripple_status':   status,          # 'pass' | 'pass_derated' | 'fail'
            'ripple_headroom_pct': headroom,
            'lifetime':        r['lifetime_raw'],
            'lifetime_temp_C': r.get('lifetime_temp_C'),   # temp the rated endurance L0 is specified at
            'op_temp':         r['op_temp_raw'],
            'op_temp_max_C':   r.get('op_temp_max_C'),     # numeric rated max temp (e.g. 105)
            'Rth_ca_CW':       Rth_ca,                     # case-to-ambient thermal resistance estimate
            'lead_spacing_mm': r['lead_spacing_mm'],
            'diameter_mm':     r['diameter_mm'],
            'height_mm':       r['height_mm'],
            'aec_q200':        r['aec_q200'],
            'rohs':            r['rohs'],
            'datasheet_url':   r['datasheet_url'],
        })

    # Sort: passing first, then by headroom desc, then by ESR asc
    rows.sort(key=lambda x: (
        0 if x['ripple_pass'] else 1,
        -(x['ripple_headroom_pct'] or -999),
        x['esr_each_ohm'],
    ))
    return rows
