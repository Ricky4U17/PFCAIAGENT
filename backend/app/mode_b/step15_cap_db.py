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

    # ── Method 1: Arrhenius from datasheet ESR ────────────────────────────
    esr_lf1 = esr_db if esr_db > 0 else (tan_d / (2 * math.pi * 120 * C_F))
    esr_hf1 = esr_lf1 * 0.595            # typical HF/LF ratio (0.138/0.232)
    P1      = I_LF**2 * esr_lf1 + I_HF**2 * esr_hf1
    dT1     = P1 * Rth
    Tc1     = Tamb + dT1
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

    # ── Governing (minimum) ───────────────────────────────────────────────
    lives = [m1['life_years'], m2['life_years'], m3['life_years']]
    min_yr = min(lives)
    gov_idx = lives.index(min_yr)
    gov_names = ['Method 1', 'Method 2', 'Method 3']

    return {
        'method1': m1, 'method2': m2, 'method3': m3,
        'min_life_years': round(min_yr, 1),
        'min_life_hours': round(min_yr * HOURS_PER_YEAR),
        'pass_15yr': min_yr >= LIFE_TARGET_YR,
        'governing_method': gov_names[gov_idx],
        'Tamb_C': Tamb, 'Vout_V': Vout,
        'qty': qty,
        'I_LF_per_cap_A': round(I_LF, 4),
        'I_HF_per_cap_A': round(I_HF, 4),
    }

_DB: list | None = None

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

    # Parallel ESR
    rows = []
    for r in matched:
        esr_each  = r['esr_ohm'] or 0.0
        esr_par   = esr_each / n if n > 0 else esr_each
        V_esr_pk  = round(I_total_A * esr_par, 3)

        rated_rip = r.get('ripple_120hz_A')
        rip_pass  = (I_per_cap <= rated_rip) if rated_rip else None
        headroom  = round((rated_rip - I_per_cap) / rated_rip * 100, 1) if rated_rip else None

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
            'V_esr_pk_V':      V_esr_pk,
            'I_rms_per_cap_A': round(I_per_cap, 3),
            'I_rated_120hz_A': rated_rip,
            'ripple_pass':     rip_pass,
            'ripple_headroom_pct': headroom,
            'lifetime':        r['lifetime_raw'],
            'op_temp':         r['op_temp_raw'],
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
