"""
Vendor-implied ESR(T, f) model for aluminium-electrolytic DC-bus capacitors
===========================================================================
The datasheet tan δ is a MAX value at 20 °C / 120 Hz, but the electrolyte resistance (which
dominates ESR at 120 Hz) is strongly NTC — at a 50–70 °C core the real ESR is roughly half the
20 °C figure. Computing losses with the cold max ESR overstates self-heating, understates the
allowable ripple current, and is inconsistent with the manufacturer lifetime model ("Life Time
Period"), whose ΔTj = ΔT0·(I_eq/I0)² relation already embeds the vendor's HOT resistance.

Model (designer decision 2026-07-14) — every number traceable to the part's own datasheet row:

  Cold anchor  (20 °C):           ESR20   = tan δ_max / (2π·120·C)      [or the DB ESR column]
  Hot anchor   (T_max + ΔT0):     ESR_hot = ΔT0 / (I_rated² · R_th)
      — the resistance the vendor's OWN rated-ripple thermal design implies at the endurance
        test condition. This is the same relation the Life Time Period model uses, so loss,
        core temperature and lifetime finally share one resistance basis.
  Between anchors: exponential in CORE temperature (electrolyte conductivity is Arrhenius):
      ESR_LF(T) = ESR20 · exp(-λ·(T-20)),  λ = ln(ESR20/ESR_hot)/(T_hot-20),  clamped to
      [ESR_hot, ESR20].

  HF (switching-frequency) branch — its own two anchors, same interpolation:
      cold: 0.595·ESR20            (typical HF/LF ratio at 20 °C, e.g. 0.138/0.232)
      hot:  ESR_hot / k_f²         (k_f = rated HF/120 Hz ripple ratio from the datasheet,
                                    e.g. Rubycon HXK 1.40 — the frequency-multiplier row is the
                                    vendor's own ESR(f) statement at the hot rated condition)

  Core temperature: fixed point  T_core = T_amb + (I_LF²·ESR_LF(T) + I_HF²·ESR_HF(T))·R_th.
  ESR is NTC ⇒ negative feedback ⇒ converges in 2–4 iterations.

  Temperature multiplier (allowed ripple vs ambient): the model-implied
      K(T_amb) = I_allow/I_rated = sqrt(ΔT_allow/(R_th·ESR_LF(T_limit)))/I_rated
  reproduces the vendor-published ripple temperature multipliers (verified ≈√(ΔT_allow/ΔT0) at
  the hot end). Where a series' PUBLISHED multiplier table is entered in VENDOR_TEMP_MULTIPLIERS
  below it takes precedence (guaranteed data > model). NOTE: published multiplier tables are
  used LITERALLY as current allowances — they are NOT decoded into ESR, because vendors mix the
  allowed-core-rise growth and the ESR(T) effect inside K in vendor-specific ways.

Fallback ladder: no I_rated on the record → no hot anchor → ESR stays at the 20 °C value
(today's conservative behaviour) and the model is flagged 'esr20_only'.
"""
from __future__ import annotations
import math
from typing import Optional

# HF/LF ESR ratio at 20 °C (typical, e.g. 0.138/0.232) and default HF ripple-frequency multiplier
HF_LF_RATIO_20C = 0.595
KF_DEFAULT      = 1.40

# ── Optional per-series VENDOR-PUBLISHED ripple temperature multipliers ───────────────────────
# Keyed by (manufacturer_substring, series_substring), values = [(T_amb_C, K), ...] EXACTLY as
# printed in the series datasheet/catalog. Used literally as I_allow = K(T_amb)·I_rated.
# Empty by default — ADD ROWS ONLY FROM A VERIFIED DATASHEET TABLE (do not estimate here; the
# model-implied K(T_amb) below covers every part without published data).
VENDOR_TEMP_MULTIPLIERS: dict = {
    # example (verify against the live datasheet before enabling):
    # ("cornell", "380LX"): [(45, 2.2), (65, 1.7), (85, 1.0)],
}


def build_esr_model(cap: dict, Rth: float, dT0: float) -> dict:
    """Build the ESR(T,f) model from a cap DB record (or selected_cap-like dict).

    cap keys used: esr_ohm | ESR_each_mohm, tan_delta, capacitance_uF | value_uF,
                   ripple_120hz_A | I_rated_A, ripple_hf_A, op_temp_max_C | temp_rating_C.
    Rth [°C/W] and dT0 [°C] are the package-type values (10/5 snap-in, 15/10 radial) — the SAME
    ones the Life Time Period model uses, keeping one thermal basis.
    """
    C_uF  = float(cap.get("capacitance_uF") or cap.get("value_uF") or 470)
    tmax  = float(cap.get("op_temp_max_C") or cap.get("temp_rating_C") or 105)

    esr20 = cap.get("esr_ohm")
    if esr20 is None and cap.get("ESR_each_mohm"):
        esr20 = float(cap["ESR_each_mohm"]) / 1000.0
    if not esr20 or esr20 <= 0:
        tan_d = float(cap.get("tan_delta") or 0.15)
        esr20 = tan_d / (2 * math.pi * 120 * C_uF * 1e-6)
    esr20 = float(esr20)

    irated = cap.get("ripple_120hz_A") or cap.get("I_rated_A")
    rhf    = cap.get("ripple_hf_A")
    kf     = (float(rhf) / float(irated)) if (rhf and irated) else KF_DEFAULT
    kf     = max(1.0, kf)

    T_hot  = tmax + dT0
    if irated and float(irated) > 0 and Rth > 0:
        esr_hot = dT0 / (float(irated) ** 2 * Rth)
        esr_hot = min(esr_hot, esr20)               # never above the cold max
        source  = "vendor_implied"
    else:
        esr_hot = esr20                              # no hot anchor → flat (today's behaviour)
        source  = "esr20_only"

    lam = (math.log(esr20 / esr_hot) / max(T_hot - 20.0, 1e-9)) if esr_hot < esr20 else 0.0

    esr_hf20  = HF_LF_RATIO_20C * esr20
    esr_hfhot = min(esr_hot / (kf * kf), esr_hf20)
    lam_hf = (math.log(esr_hf20 / esr_hfhot) / max(T_hot - 20.0, 1e-9)) if esr_hfhot < esr_hf20 else 0.0

    return {"esr20": esr20, "esr_hot": esr_hot, "T_hot": T_hot, "lam": lam,
            "esr_hf20": esr_hf20, "esr_hf_hot": esr_hfhot, "lam_hf": lam_hf,
            "kf": kf, "Rth": Rth, "dT0": dT0, "tmax": tmax,
            "I_rated_A": float(irated) if irated else None, "source": source}


def esr_lf_at(m: dict, T_core: float) -> float:
    """LF (120 Hz) ESR at the given CORE temperature, clamped to [hot, cold] anchors."""
    v = m["esr20"] * math.exp(-m["lam"] * (T_core - 20.0))
    return min(max(v, m["esr_hot"]), m["esr20"])


def esr_hf_at(m: dict, T_core: float) -> float:
    """HF (switching) ESR at the given CORE temperature, clamped to its anchors."""
    v = m["esr_hf20"] * math.exp(-m["lam_hf"] * (T_core - 20.0))
    return min(max(v, m["esr_hf_hot"]), m["esr_hf20"])


def solve_core_temp(m: dict, I_lf: float, I_hf: float, T_amb: float,
                    iters: int = 6, tol: float = 0.05) -> dict:
    """Fixed-point solve of T_core = T_amb + (I_LF²·ESR_LF(T) + I_HF²·ESR_HF(T))·R_th.
    NTC ESR ⇒ negative feedback ⇒ monotone convergence in a few iterations."""
    T = T_amb
    for _ in range(iters):
        el, eh = esr_lf_at(m, T), esr_hf_at(m, T)
        P  = I_lf * I_lf * el + I_hf * I_hf * eh
        Tn = T_amb + P * m["Rth"]
        if abs(Tn - T) < tol:
            T = Tn; break
        T = Tn
    el, eh = esr_lf_at(m, T), esr_hf_at(m, T)
    P = I_lf * I_lf * el + I_hf * I_hf * eh
    return {"T_core": T, "dT": T - T_amb, "P_W": P,
            "esr_lf": el, "esr_hf": eh, "source": m["source"]}


def temp_multiplier(m: dict, T_amb: float, mfr: str = "", series: str = "") -> dict:
    """Allowed-ripple temperature multiplier K(T_amb) so I_allow = K·I_rated.

    A VENDOR-PUBLISHED table (VENDOR_TEMP_MULTIPLIERS) takes precedence when present (linear
    interpolation, clamped to the table ends). Otherwise the MODEL-IMPLIED multiplier:
    allowed core = T_max + ΔT0 ⇒ ΔT_allow = T_max + ΔT0 − T_amb evaluated with the hot-limit
    ESR ⇒ K = sqrt(ΔT_allow/(R_th·ESR_LF(T_limit)))/I_rated. Reduces to K=1 at T_amb = T_max."""
    key_m = (mfr or "").lower(); key_s = (series or "").lower()
    for (km, ks), table in VENDOR_TEMP_MULTIPLIERS.items():
        if km in key_m and ks and ks.lower() in key_s:
            pts = sorted(table)
            if T_amb <= pts[0][0]:  K = pts[0][1]
            elif T_amb >= pts[-1][0]: K = pts[-1][1]
            else:
                K = pts[-1][1]
                for (t0, k0), (t1, k1) in zip(pts, pts[1:]):
                    if t0 <= T_amb <= t1:
                        K = k0 + (k1 - k0) * (T_amb - t0) / max(t1 - t0, 1e-9); break
            return {"K": float(K), "source": "vendor_table"}
    if not m.get("I_rated_A"):
        return {"K": 1.0, "source": "no_rating"}
    dT_allow = max(m["tmax"] + m["dT0"] - T_amb, 0.0)
    T_limit  = m["tmax"] + m["dT0"]                    # core at the allowed limit
    i_allow  = math.sqrt(dT_allow / (m["Rth"] * esr_lf_at(m, T_limit))) if dT_allow > 0 else 0.0
    # Evaluated at the hot-limit ESR this reduces to the standard K = √(ΔT_allow/ΔT0) convention
    # (K(T_max) = 1 exactly). Clamped at 2.5 — the upper range of published vendor multiplier
    # tables — because longevity is gated separately by the Life Time Period model.
    K = min(max(i_allow / m["I_rated_A"], 0.0), 2.5)
    return {"K": K, "source": "model_implied"}
