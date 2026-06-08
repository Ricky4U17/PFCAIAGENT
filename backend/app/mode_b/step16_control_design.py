"""
step16_control_design.py
PFC Control Loop Design — Step 16 calculation engine.

Ports the FAN9672 Control Design Tool v4 transfer-function math to Python so
the report generator can produce Bode plots, stability margins, and component
tables using the same equations as the browser tool.

Transfer functions implemented (single-phase equivalent, per-phase inductance):
  plantI   — duty → inductor current  (same as JS plantI)
  GvpV     — voltage plant             (same as JS GvpV)
  TiUnc    — uncompensated inner loop  (plant × current-sense filter)
  Ti       — compensated inner loop    (TiUnc × Type-II compensator)
  TvBase   — uncompensated outer loop  (inner closed × voltage plant × Gmod)
  Tv       — compensated outer loop    (TvBase × OTA compensator)

All frequency sweeps use 400 log-spaced points per decade.
"""
from __future__ import annotations
import math
import cmath
import numpy as np
from typing import Dict, List, Tuple

PI   = math.pi
SQRT2 = math.sqrt(2)

# ── IC constants (FAN9672) ────────────────────────────────────────────────────
FIXED = dict(
    GMI      = 88e-6,   # current-error amplifier trans-conductance [S]
    GMV      = 100e-6,  # voltage-error amplifier trans-conductance [S]
    VRAMP    = 5.0,     # internal PWM ramp [V]
    VREF     = 2.5,     # internal voltage reference [V]
    NCH      = 2,       # default interleaved phases
    Gmax     = 2.0,     # GMOD clip level
    RM       = 7500.0,  # GMOD bias resistor [Ω]
    KRM      = 6000.0,  # GMOD numerator constant
    KRLPK    = 2.465,   # RLPK scale factor
    Kavg     = 0.9003,  # 2-phase averaging factor
)

# ── Default operating points (matches Python DEFAULT_OPS / JS VACS) ──────────
LOW_VACS  = [90, 110, 120, 132]
HIGH_VACS = [180, 200, 220, 230, 264]
ALL_VACS  = LOW_VACS + HIGH_VACS


# ── Complex-number helpers (matching JS cadd/cmul/cdiv style) ─────────────────

def _Gid(L_H: float, C_F: float, ESR_ohm: float, DCR_ohm: float,
         Vout: float, Pout: float, Vin_rms: float, w: float) -> complex:
    """Duty → inductor-current gain Gid(jω) — matches JS plantI()."""
    Vpk = SQRT2 * Vin_rms
    D   = max(0.0, 1.0 - Vpk / Vout)
    Dp  = 1.0 - D
    RL  = Vout**2 / Pout                          # load resistance per phase

    Kf  = (Vout / L_H) * ((RL + 2*ESR_ohm) / (RL + ESR_ohm))
    wz  = 1.0 / (C_F * (RL/2 + ESR_ohm))
    den = L_H * C_F * (RL + ESR_ohm)

    a1  = (C_F*(DCR_ohm*(RL+ESR_ohm) + RL*ESR_ohm*Dp**2) + L_H) / den
    a0  = (Dp**2 * RL + DCR_ohm) / den

    num = complex(Kf * wz, Kf * w)               # Kf · (wz + jw)
    denom = complex(a0 - w**2, a1 * w)           # (a0 - w²) + j·a1·w
    return num / denom


def _Gvp(L_H: float, C_F: float, ESR_ohm: float,
         Vout: float, Pout: float, Vin_rms: float, w: float) -> complex:
    """Voltage-to-output plant GvpV(jω) — matches JS GvpV()."""
    Vpk = SQRT2 * Vin_rms
    Dp  = Vpk / Vout
    RL  = Vout**2 / Pout
    fR  = RL * Dp**2 / (2*PI * L_H/2)
    wR  = 2*PI * fR

    num  = complex(1, w*C_F*ESR_ohm) * complex(1, -w/wR)
    denom = complex(2/RL, w*C_F)
    return num / denom


def _Hcs(RF: float, CF: float, w: float) -> complex:
    """Current-sense RC filter Hcs(jω)."""
    fRC = 1.0 / (2*PI * RF * CF)
    return 1.0 / complex(1.0, w/fRC) if fRC > 0 else complex(1.0)


def _Gmi_T2(GMI: float, RIC: float, C1: float, C2: float, f: float) -> complex:
    """Type-II current compensator transfer function."""
    w  = 2*PI * f
    fz = 1.0 / (2*PI * RIC * C1)
    fp = 1.0 / (2*PI * RIC * C2) if C2 > 0 else 1e12
    num   = complex(1.0, -fz/f)
    denom = complex(1.0,  f/fp)
    return GMI * RIC * (num / denom)


def _Hota_T2(GMV: float, R2: float, C1: float, C3: float,
             R1fb: float, R4fb: float, f: float) -> complex:
    """Type-II voltage OTA compensator transfer function."""
    Hdiv = R4fb / (R1fb + R4fb)
    fz   = 1.0 / (2*PI * R2 * C1)
    fp   = (C1+C3) / (2*PI * R2 * C1 * C3) if C3 > 0 else 1.0/(2*PI*R2*C1)
    num   = complex(1.0, -fz/f)
    denom = complex(1.0,  f/fp)
    return GMV * R2 * Hdiv * (num / denom)


def _Hota_T3(GMV: float, R2: float, R3: float, C1: float, C2: float, C3: float,
             R1fb: float, R4fb: float, f: float) -> complex:
    """Type-III voltage OTA (SLVA662 Method B) — direct port of JS HotaStd(type3)."""
    P    = R1fb * R4fb / (R1fb + R4fb)
    Hdiv = R4fb / (R1fb + R4fb)
    fz1  = 1.0 / (2*PI * R2 * C1)
    fz2  = 1.0 / (2*PI * (R1fb + R3) * C2) if C2 > 0 else 1e12
    fp1  = (C1 + C3) / (2*PI * R2 * C1 * C3) if C3 > 0 else 1e12
    fp2  = 1.0 / (2*PI * (R3 + P) * C2) if C2 > 0 else 1e12
    Kc   = GMV * R2 * Hdiv * (fp2 - fz1) / fp2
    num  = complex(1.0, -fz1/f) * complex(1.0, f/fz2)
    den  = complex(1.0,  f/fp1) * complex(1.0, f/fp2)
    return Kc * (num / den)


def _nearest_std(v: float, series: str = 'E96') -> float:
    """Return nearest E96/E24 standard value."""
    E96 = [1.00,1.02,1.05,1.07,1.10,1.13,1.15,1.18,1.21,1.24,1.27,1.30,
           1.33,1.37,1.40,1.43,1.47,1.50,1.54,1.58,1.62,1.65,1.69,1.74,
           1.78,1.82,1.87,1.91,1.96,2.00,2.05,2.10,2.15,2.21,2.26,2.32,
           2.37,2.43,2.49,2.55,2.61,2.67,2.74,2.80,2.87,2.94,3.01,3.09,
           3.16,3.24,3.32,3.40,3.48,3.57,3.65,3.74,3.83,3.92,4.02,4.12,
           4.22,4.32,4.42,4.53,4.64,4.75,4.87,4.99,5.11,5.23,5.36,5.49,
           5.62,5.76,5.90,6.04,6.19,6.34,6.49,6.65,6.81,6.98,7.15,7.32,
           7.50,7.68,7.87,8.06,8.25,8.45,8.66,8.87,9.09,9.31,9.53,9.76]
    E24 = [1.0,1.1,1.2,1.3,1.5,1.6,1.8,2.0,2.2,2.4,2.7,3.0,
           3.3,3.6,3.9,4.3,4.7,5.1,5.6,6.2,6.8,7.5,8.2,9.1]
    vals = E96 if series == 'E96' else E24
    if v <= 0:
        return float('nan')
    d    = math.floor(math.log10(v))
    best = v
    err  = 1e99
    for k in range(d-1, d+2):
        for m in vals:
            cand = m * 10**k
            e    = abs(math.log(v/cand))
            if e < err:
                err  = e
                best = cand
    return best


# ── Frequency sweep ───────────────────────────────────────────────────────────

def _sweep(fn, f1: float, f2: float, n: int = 400) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Log-spaced frequency sweep.  Returns (f_Hz, mag_dB, phase_deg)."""
    freqs = np.logspace(math.log10(f1), math.log10(f2), n)
    mag   = np.zeros(n)
    ph    = np.zeros(n)
    prev  = 0.0
    for i, f in enumerate(freqs):
        z    = fn(f)
        m    = abs(z)
        ang  = math.degrees(cmath.phase(z))
        # phase unwrap
        while ang - prev >  180: ang -= 360
        while ang - prev < -180: ang += 360
        prev = ang
        mag[i] = 20 * math.log10(max(m, 1e-30))
        ph[i]  = ang
    return freqs, mag, ph


def _margins(f_arr: np.ndarray, mag_arr: np.ndarray,
             ph_arr: np.ndarray) -> Dict[str, float]:
    """Extract crossover frequency, phase margin, and gain margin."""
    fc = float('nan'); pm = float('nan'); gm = float('nan'); fg = float('nan')
    # crossover: where mag crosses 0 dB
    for i in range(len(f_arr)-1):
        if mag_arr[i] * mag_arr[i+1] <= 0:
            t  = -mag_arr[i] / (mag_arr[i+1] - mag_arr[i])
            fc = float(f_arr[i] + t*(f_arr[i+1]-f_arr[i]))
            pm = float(180 + ph_arr[i] + t*(ph_arr[i+1]-ph_arr[i]))
            break
    # gain margin: where phase crosses -180°
    for i in range(len(f_arr)-1):
        if (ph_arr[i]+180) * (ph_arr[i+1]+180) <= 0:
            t  = -(ph_arr[i]+180) / ((ph_arr[i+1]+180) - (ph_arr[i]+180))
            fg = float(f_arr[i] + t*(f_arr[i+1]-f_arr[i]))
            m  = mag_arr[i] + t*(mag_arr[i+1]-mag_arr[i])
            gm = float(-m)
            break
    return {'fc': fc, 'pm': pm, 'gm': gm, 'fg': fg}


# ── Main design function ──────────────────────────────────────────────────────

def design_control_loops(
    L_uH:             float,      # per-phase inductance (µH)
    DCR_mOhm:         float,      # per-phase DCR @ 100°C (mΩ)
    C_uF:             float,      # total output capacitance (µF)
    ESR_mOhm:         float,      # parallel ESR of cap bank (mΩ)
    Vout_V:           float,      # output bus voltage (V)
    fsw_Hz:           float,      # switching frequency (Hz)
    Pout_lo_W:        float = 1700,
    Pout_hi_W:        float = 3600,
    eta_lo:           float = 0.945,
    eta_hi:           float = 0.965,
    nch:              int   = 2,
    RCS_mOhm:         float = 15.0,
    kmax:             float = 1.49,
    js_design_state:  dict | None = None,  # actual values from the JS tool
) -> dict:
    """
    Run the full Step-16 control-loop design.
    Returns a structured dict consumed by generate_step16.py.
    """
    L_H      = L_uH   * 1e-6
    DCR_ohm  = DCR_mOhm * 1e-3
    C_F      = C_uF   * 1e-6
    ESR_ohm  = ESR_mOhm * 1e-3
    rcs      = RCS_mOhm * 1e-3

    GMI = FIXED['GMI']; GMV = FIXED['GMV']
    VRAMP = FIXED['VRAMP']

    # ── Override component values from JS tool if provided ───────────────────
    # The JS tool may have been configured with Type 3 OTA or custom-tuned
    # values that differ from Python's auto-sizing.  When js_design_state is
    # present, use its std component values and compensator type verbatim so
    # the Python report matches what the designer sees in the browser tool.
    js = js_design_state or {}
    v_type = js.get('vType', 'type2')            # 'type2' or 'type3'
    R1fb_js = float(js.get('r1fb', 1.21e6))
    R4fb_js = float(js.get('r4fb', 23.2e3))
    RF_js   = float(js.get('rf',   2000.0))
    CF_js   = float(js.get('cf',   470e-12))

    # Current loop (Type 2) — use JS std values if available
    dci_std = js.get('dci_std') or {}
    RIC_js  = float(dci_std.get('RIC', 0)) if dci_std else 0
    C1i_js  = float(dci_std.get('C1',  0)) if dci_std else 0
    C2i_js  = float(dci_std.get('C2',  0)) if dci_std else 0

    # Voltage loop — JS std values depend on type
    dcv_std = js.get('dcv_std') or {}
    R2_js   = float(dcv_std.get('R2',  0)) if dcv_std else 0
    R3_js   = float(dcv_std.get('R3',  0)) if dcv_std else 0
    C1v_js  = float(dcv_std.get('C1',  0)) if dcv_std else 0
    C2v_js  = float(dcv_std.get('C2',  0)) if dcv_std else 0
    C3v_js  = float(dcv_std.get('C3',  0)) if dcv_std else 0

    # ── Plant frequencies ────────────────────────────────────────────────────
    f_lc   = 1.0 / (2*PI * math.sqrt(L_H * C_F))
    f_esr  = 1.0 / (2*PI * ESR_ohm * C_F)

    # RHP zeros at worst-case (90 Vac, LL; 180 Vac, HL)
    def _rhp(Vin_rms, Pout):
        Vpk = SQRT2 * Vin_rms
        Dp  = max(0.01, Vpk / Vout_V)
        RL  = Vout_V**2 / Pout
        return RL * Dp**2 / (2*PI * L_H)

    f_rhpz_ll = _rhp(90,  Pout_lo_W)   # worst-case for voltage-loop BW
    f_rhpz_hl = _rhp(180, Pout_hi_W)

    # ── Current-loop target ──────────────────────────────────────────────────
    fci    = float(js.get('fci_Hz', fsw_Hz / 8)) if js else fsw_Hz / 8
    cfz    = fci / 5
    cfp    = fsw_Hz / 4

    R1fb  = R1fb_js; R4fb = R4fb_js
    RF_cs = RF_js;   CF_cs = CF_js

    def _Ti_unc_at(vac, pout, f):
        w   = 2*PI * f
        Gid = _Gid(L_H, C_F, ESR_ohm, DCR_ohm, Vout_V, pout, vac, w)
        Hcs = _Hcs(RF_cs, CF_cs, w)
        return Gid * Hcs * rcs / VRAMP

    # Use JS-provided std values if available, else auto-size
    if RIC_js > 0:
        RIC = RIC_js; C1 = C1i_js; C2 = C2i_js
    else:
        Tu90 = _Ti_unc_at(90, Pout_lo_W, fci)
        mTu  = abs(Tu90)
        kap  = math.sqrt(1 + (cfz/fci)**2) / math.sqrt(1 + (fci/cfp)**2)
        RIC  = _nearest_std(1.0 / (mTu * GMI * kap), 'E96')
        C1   = _nearest_std(1.0 / (2*PI * cfz * RIC), 'E24')
        C2   = _nearest_std(1.0 / (2*PI * cfp * RIC), 'E24')

    # ── Voltage-loop target ──────────────────────────────────────────────────
    fcv   = float(js.get('fcv_Hz', min(fsw_Hz / 10, f_rhpz_ll / 5, 25.0))) if js else min(fsw_Hz / 10, f_rhpz_ll / 5, 25.0)
    vfz1  = fcv / 3
    vfp1  = f_esr
    Hdiv  = R4fb / (R1fb + R4fb)

    def _TvBase_at(vac, pout, f):
        w    = 2*PI * f
        Ti   = _Ti_unc_at(vac, pout, f) * _Gmi_T2(GMI, RIC, C1, C2, f)
        Ti_n = Ti / nch
        Gicl = Ti_n / (1 + Ti_n)
        Gvp  = _Gvp(L_H, C_F, ESR_ohm, Vout_V, pout, vac, w)
        Gmod = kmax * (pout / Vout_V) / VRAMP
        return Gicl * Gvp * Gmod

    # Use JS-provided std values if available, else auto-size
    if R2_js > 0:
        R2 = R2_js; R3 = R3_js; C1v = C1v_js; C2v = C2v_js; C3v = C3v_js
    else:
        TvB_90  = _TvBase_at(90, Pout_lo_W, fcv)
        G_req   = 1.0 / abs(TvB_90)
        R2      = _nearest_std(G_req / (GMV * Hdiv),           'E96')
        C1v     = _nearest_std(1.0 / (2*PI * vfz1 * R2),       'E24')
        C3v     = _nearest_std(1.0 / (2*PI * vfp1 * R2),       'E24')
        R3 = 0.0; C2v = 0.0
        v_type  = 'type2'   # Python auto-sizing is always Type 2

    # ── Frequency sweeps for Bode plots ──────────────────────────────────────
    def _Ti_sw(vac, pout):
        return _sweep(
            lambda f: _Ti_unc_at(vac, pout, f) * _Gmi_T2(GMI, RIC, C1, C2, f),
            100, min(fsw_Hz*0.9, 3e5), 400)

    def _make_Hota(f):
        if v_type == 'type3' and R3 > 0 and C2v > 0:
            return _Hota_T3(GMV, R2, R3, C1v, C2v, C3v, R1fb, R4fb, f)
        return _Hota_T2(GMV, R2, C1v, C3v, R1fb, R4fb, f)

    def _Tv_sw(vac, pout):
        return _sweep(
            lambda f: _TvBase_at(vac, pout, f) * _make_Hota(f),
            0.5, 1e6, 500)

    sw_i_ll = _Ti_sw(90,  Pout_lo_W)
    sw_i_hl = _Ti_sw(180, Pout_hi_W)
    sw_v_ll = _Tv_sw(90,  Pout_lo_W)
    sw_v_hl = _Tv_sw(180, Pout_hi_W)

    mg_i_ll = _margins(*sw_i_ll)
    mg_i_hl = _margins(*sw_i_hl)
    mg_v_ll = _margins(*sw_v_ll)
    mg_v_hl = _margins(*sw_v_hl)

    # ── Stability scorecard across all 9 operating points ────────────────────
    scorecard = []
    for vac in ALL_VACS:
        pout = Pout_lo_W if vac <= 132 else Pout_hi_W
        mi_f, mi_m, mi_p = _Ti_sw(vac, pout)
        mv_f, mv_m, mv_p = _Tv_sw(vac, pout)
        mi = _margins(mi_f, mi_m, mi_p)
        mv = _margins(mv_f, mv_m, mv_p)
        rej_120 = -float(np.interp(120, mv_f, mv_m))  # 120 Hz rejection
        scorecard.append({
            'Vin_rms': vac, 'Pout': pout,
            'line': 'LL' if vac <= 132 else 'HL',
            'fc_i': mi['fc'], 'pm_i': mi['pm'], 'gm_i': mi['gm'],
            'fc_v': mv['fc'], 'pm_v': mv['pm'], 'gm_v': mv['gm'],
            'rej_120': rej_120,
            'pass': (mi['pm'] >= 45 and mv['pm'] >= 55 and rej_120 >= 20),
        })

    # ── RHP zero / critical-frequency table ──────────────────────────────────
    rhpz_table = []
    for vac in ALL_VACS:
        pout = Pout_lo_W if vac <= 132 else Pout_hi_W
        rhpz_table.append({'Vin_rms': vac, 'Pout': pout,
                           'f_rhpz_i': _rhp(vac, pout),
                           'f_rhpz_v': _rhp(vac, pout) * 2})

    # ── Soft-start capacitor ─────────────────────────────────────────────────
    t_ss  = 0.050   # 50 ms default soft-start
    I_ss  = 20e-6   # FAN9672 SS pin current
    V_ss  = 5.0     # SS ramp limit
    css_calc = I_ss * t_ss / V_ss
    css = _nearest_std(css_calc, 'E24')

    return {
        # Plant parameters
        'L_uH':       L_uH,
        'DCR_mOhm':   DCR_mOhm,
        'C_uF':       C_uF,
        'ESR_mOhm':   ESR_mOhm,
        'Vout_V':     Vout_V,
        'fsw_Hz':     fsw_Hz,
        'Pout_lo_W':  Pout_lo_W,
        'Pout_hi_W':  Pout_hi_W,
        'nch':        nch,
        'RCS_mOhm':   RCS_mOhm,
        # Key frequencies
        'f_lc_Hz':       f_lc,
        'f_esr_Hz':      f_esr,
        'f_rhpz_ll_Hz':  f_rhpz_ll,
        'f_rhpz_hl_Hz':  f_rhpz_hl,
        # Current loop
        'fci_Hz':  fci,
        'RIC':     RIC,
        'C1_cur':  C1,
        'C2_cur':  C2,
        'sw_i_ll': sw_i_ll,
        'sw_i_hl': sw_i_hl,
        'mg_i_ll': mg_i_ll,
        'mg_i_hl': mg_i_hl,
        # Voltage loop
        'v_type':  v_type,          # 'type2' or 'type3'
        'fcv_Hz':  fcv,
        'R2':      R2,
        'R3':      R3,              # Type 3 only (0 for Type 2)
        'C1_vol':  C1v,
        'C2_vol':  C2v,             # Type 3 only (0 for Type 2)
        'C3_vol':  C3v,
        'R1fb':    R1fb,
        'R4fb':    R4fb,
        'sw_v_ll': sw_v_ll,
        'sw_v_hl': sw_v_hl,
        'mg_v_ll': mg_v_ll,
        'mg_v_hl': mg_v_hl,
        # Scorecard
        'scorecard':  scorecard,
        'rhpz_table': rhpz_table,
        # Auxiliary
        'css_calc': css_calc,
        'css':      css,
        't_ss_ms':  t_ss * 1000,
    }
