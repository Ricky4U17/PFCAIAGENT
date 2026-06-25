"""
Layer 3 - Visualization for the PFC semiconductor loss model
============================================================
Pure presentation layer. It calls the calculation/simulation backend
(`pfc_loss_model_step3_local.py`) and renders four figures:

    waveforms            : operating-point waveforms at one Vac (2x2 panel)
    loss_breakdown       : per-mechanism semiconductor loss bar chart at one Vac
    losses_vs_vac        : FET / diode / bridge / total semi loss across the Vac sweep
    temperatures_vs_vac  : junction temperatures across the Vac sweep

`build_step4_visuals(cfg, ...)` returns a dict {name: png_path}. It contains NO
loss physics - everything numeric comes from the backend, so the three layers stay
cleanly separated.
"""
from __future__ import annotations
import os, sys, importlib.util
import numpy as np
import matplotlib
matplotlib.use("Agg")            # safe default; the notebook re-enables inline display itself
import matplotlib.pyplot as plt

_BACKEND = None
BACKEND_FILENAME = "pfc_loss_model_step3_local.py"

def _get_backend(backend=None):
    """Locate the calculation backend. Accepts an injected module, else loads the file
    from the current directory or next to this module."""
    global _BACKEND
    if backend is not None:
        return backend
    if _BACKEND is not None:
        return _BACKEND
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(os.getcwd(), BACKEND_FILENAME), os.path.join(here, BACKEND_FILENAME)):
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("pfc_backend_for_viz", path)
            m = importlib.util.module_from_spec(spec)
            sys.modules["pfc_backend_for_viz"] = m
            spec.loader.exec_module(m)
            _BACKEND = m
            return m
    raise FileNotFoundError(f"Could not find {BACKEND_FILENAME} for the visualization backend.")

# colour-by-device so the same device reads the same colour across every figure
_C = {"fet": "#3b6ec0", "diode": "#d2356b", "bridge": "#1f9e89", "total": "#444441", "accent": "#e8a33d"}


def _finish(fig, path, show):
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return path


def plot_waveforms(result, vac, path, show=False):
    """2x2 operating-point panel. `result` must come from simulate_point(..., return_waveforms=True)."""
    w = result["waveforms"]
    ang = w["theta_deg"]
    fig, axs = plt.subplots(2, 2, figsize=(13, 8))
    fig.suptitle(f"PFC waveforms at Vac = {vac:.0f} Vrms "
                 f"(Po={result['Po']:.0f} W, eta={result['eta_in_%']:.1f}%, PF={result['PF_in']:.3f})",
                 fontsize=14)

    # (0,0) input voltage + duty
    ax = axs[0, 0]; ax2 = ax.twinx()
    ax.plot(ang, w["vin"], color=_C["fet"], label="Vin")
    ax2.plot(ang, w["duty"], color=_C["diode"], label="Duty")
    ax.set_title("Input voltage and duty vs line angle")
    ax.set_xlabel("Line angle [deg]"); ax.set_ylabel("Vin [V]", color=_C["fet"])
    ax2.set_ylabel("Duty", color=_C["diode"]); ax.grid(True, alpha=0.3)

    # (0,1) per-channel current with the switching-ripple band shaded
    ax = axs[0, 1]
    ax.fill_between(ang, w["i_on"], w["i_off"], color=_C["fet"], alpha=0.18,
                    label="turn-on..turn-off band")
    ax.plot(ang, w["i_ch"], color=_C["fet"], lw=2, label="per-channel current")
    if np.any(w["dcm_mask"]):
        ax.fill_between(ang, 0, ax.get_ylim()[1], where=w["dcm_mask"],
                        color=_C["accent"], alpha=0.15, label="DCM region")
    ax.set_title("Per-channel current and switching-instant band")
    ax.set_xlabel("Line angle [deg]"); ax.set_ylabel("Current [A]")
    ax.grid(True, alpha=0.3); ax.legend(fontsize=8)

    # (1,0) instantaneous TOTAL device power (each averages to the bar-chart total)
    ax = axs[1, 0]
    ax.plot(ang, w["p_fet_total_t"], color=_C["fet"], label=f"FET ({result['P_FET_total']:.1f} W)")
    ax.plot(ang, w["p_diode_total_t"], color=_C["diode"], label=f"Diode ({result['P_DIODE_total']:.1f} W)")
    ax.plot(ang, w["p_bridge_total_t"], color=_C["bridge"], label=f"Bridge ({result['P_BRIDGE_total']:.1f} W)")
    ax.set_title("Instantaneous device power (total of all devices)")
    ax.set_xlabel("Line angle [deg]"); ax.set_ylabel("Power [W]")
    ax.grid(True, alpha=0.3); ax.legend(fontsize=8)
    ax.annotate("non-zero floor at the line zero-crossings = current-independent\n"
                "Coss (Eoss) and SiC Qc switching loss",
                xy=(0.02, 0.97), xycoords="axes fraction", va="top", fontsize=7.5,
                color=_C["total"])

    # (1,1) ripple current + DCM
    ax = axs[1, 1]
    ax.plot(ang, w["di_pp"], color=_C["fet"], label="inductor ripple di (p-p)")
    if np.any(w["dcm_mask"]):
        ax.fill_between(ang, 0, ax.get_ylim()[1], where=w["dcm_mask"],
                        color=_C["accent"], alpha=0.20, label="DCM region")
        title = "Ripple current and DCM region"
    else:
        title = "Ripple current (full CCM, no DCM)"
    ax.set_title(title); ax.set_xlabel("Line angle [deg]"); ax.set_ylabel("Ripple current [A]")
    ax.grid(True, alpha=0.3); ax.legend(fontsize=8)
    return _finish(fig, path, show)


def plot_loss_breakdown(result, vac, path, show=False):
    items = [("FET cond", result["P_FET_cond"], _C["fet"]),
             ("FET sw",   result["P_FET_sw"],   _C["fet"]),
             ("FET Coss", result["P_FET_coss"], _C["fet"]),
             ("FET RR",   result["P_FET_rr"],   _C["fet"]),
             ("FET leak", result["P_FET_leak"], _C["fet"]),
             ("Diode cond", result["P_D_cond"], _C["diode"]),
             ("Diode sw",   result["P_D_sw"],   _C["diode"]),
             ("Bridge top",    result["P_BRIDGE_top"],    _C["bridge"]),
             ("Bridge bottom", result["P_BRIDGE_bottom"], _C["bridge"]),
             ("Gate driver",   result["P_gate_driver"],   _C["total"])]
    labels = [i[0] for i in items]; vals = [i[1] for i in items]; cols = [i[2] for i in items]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    bars = ax.bar(labels, vals, color=cols, edgecolor="black", linewidth=0.6)
    for b, v in zip(bars, vals):
        if v > 0.02:
            ax.text(b.get_x() + b.get_width()/2, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_title(f"Semiconductor loss breakdown at Vac = {vac:.0f} Vrms  "
                 f"(semi total {result['P_SEMI_total']:.1f} W - inductor & cap not included)")
    ax.set_xlabel("Loss component"); ax.set_ylabel("Loss [W]")
    ax.grid(True, axis="y", alpha=0.3); plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    return _finish(fig, path, show)


def plot_losses_vs_vac(flat_rows, path, show=False):
    vac = [r["Vac"] for r in flat_rows]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(vac, [r["P_FET_total"] for r in flat_rows],    "o-", color=_C["fet"],    label="FET")
    ax.plot(vac, [r["P_DIODE_total"] for r in flat_rows],  "s-", color=_C["diode"],  label="Diode")
    ax.plot(vac, [r["P_BRIDGE_total"] for r in flat_rows], "^-", color=_C["bridge"], label="Bridge")
    ax.plot(vac, [r["P_SEMI_total"] for r in flat_rows],   "D-", color=_C["total"], lw=2, label="Semi total")
    ax.set_title("Semiconductor losses vs input voltage")
    ax.set_xlabel("Vac [Vrms]"); ax.set_ylabel("Loss [W]")
    ax.grid(True, alpha=0.3); ax.legend()
    return _finish(fig, path, show)


def plot_temperatures_vs_vac(flat_rows, path, show=False, tj_limits=None):
    vac = [r["Vac"] for r in flat_rows]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(vac, [r["Tj_FET"] for r in flat_rows],        "o-", color=_C["fet"],    label="Tj FET")
    ax.plot(vac, [r["Tj_DIODE"] for r in flat_rows],      "s-", color=_C["diode"],  label="Tj Diode")
    ax.plot(vac, [r["Tj_BRIDGE_top"] for r in flat_rows], "^-", color=_C["bridge"], label="Tj Bridge top")
    if tj_limits:
        for key, col in (("fet", _C["fet"]), ("diode", _C["diode"]), ("bridge", _C["bridge"])):
            if key in tj_limits:
                ax.axhline(tj_limits[key], color=col, ls="--", alpha=0.5)
    ax.set_title("Junction temperatures vs input voltage")
    ax.set_xlabel("Vac [Vrms]"); ax.set_ylabel("Temperature [C]")
    ax.grid(True, alpha=0.3); ax.legend()
    return _finish(fig, path, show)


def build_step4_visuals(cfg, selected_vac=90, vac_list=None, output_prefix="step4",
                        show=False, backend=None, tj_limits=None):
    """Render all four figures for a design dict `cfg`. Returns {name: png_path}."""
    be = _get_backend(backend)
    sp, mos, dio, br, th = be.design_from_dict(cfg)
    if vac_list is None:
        vac_list = cfg.get("run", {}).get("vac_list", [selected_vac])

    point = be.simulate_point(float(selected_vac), sp, mos, dio, br, th, return_waveforms=True)
    sweep = [be.simulate_point(float(v), sp, mos, dio, br, th) for v in vac_list]

    files = {
        "waveforms":           plot_waveforms(point, selected_vac, f"{output_prefix}_waveforms.png", show),
        "loss_breakdown":      plot_loss_breakdown(point, selected_vac, f"{output_prefix}_loss_breakdown.png", show),
        "losses_vs_vac":       plot_losses_vs_vac(sweep, f"{output_prefix}_losses_vs_vac.png", show),
        "temperatures_vs_vac": plot_temperatures_vs_vac(sweep, f"{output_prefix}_temperatures_vs_vac.png", show, tj_limits),
    }
    return files


if __name__ == "__main__":
    be = _get_backend()
    out = build_step4_visuals(be.EXAMPLE_DESIGN, selected_vac=90,
                              vac_list=[90, 115, 180, 230, 265], output_prefix="step4_demo", show=False)
    print("Wrote:")
    for k, v in out.items():
        print(f"  {k:20s} -> {v}")
