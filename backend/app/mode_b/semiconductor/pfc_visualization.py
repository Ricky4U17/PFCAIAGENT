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


def plot_loss_stack_vs_vac(flat_rows, path, show=False):
    """The loss BUDGET as a stack, so which mechanism dominates is visible at a glance.

    Section 7.8b already carries these numbers as a table. What a table does not show is the
    handover: conduction dominates at low line where the current is highest, switching and the
    voltage-dependent terms take over at high line. That shift is the single most useful thing a
    reviewer can know about where the design's loss actually lives, and it is one glance here
    against nine rows of arithmetic there.
    """
    vac = [r["Vac"] for r in flat_rows]
    layers = [
        ("MOSFET conduction", [r["P_FET_cond"] for r in flat_rows], _C["fet"], None),
        ("MOSFET switching", [r["P_FET_sw"] for r in flat_rows], _C["fet"], "//"),
        ("MOSFET Eoss + gate", [r["P_FET_coss"] + r.get("P_gate_driver", 0.0)
                                for r in flat_rows], _C["fet"], ".."),
        ("Diode charge into FET", [r["P_FET_rr"] for r in flat_rows], _C["accent"], None),
        ("Boost diode", [r["P_DIODE_total"] for r in flat_rows], _C["diode"], None),
        ("Bridge", [r["P_BRIDGE_total"] for r in flat_rows], _C["bridge"], None),
    ]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    bottom = np.zeros(len(vac))
    width = (min(np.diff(sorted(vac))) * 0.7) if len(vac) > 1 else 8.0
    for label, vals, colour, hatch in layers:
        v = np.asarray(vals, dtype=float)
        ax.bar(vac, v, bottom=bottom, width=width, label=label, color=colour,
               edgecolor="white", linewidth=0.6, hatch=hatch, alpha=0.95)
        bottom += v
    ax.plot(vac, bottom, "D-", color=_C["total"], lw=1.6, ms=4, label="Semi total")
    worst = int(np.argmax(bottom))
    ax.annotate(f"worst {bottom[worst]:.1f} W", (vac[worst], bottom[worst]),
                textcoords="offset points", xytext=(0, 9), ha="center",
                fontsize=9, color=_C["total"])
    ax.set_title("Semiconductor loss budget vs input voltage")
    ax.set_xlabel("Vac [Vrms]"); ax.set_ylabel("Loss [W]")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    return _finish(fig, path, show)


def plot_loss_vs_rg(cfg, path, show=False, backend=None, rg_values=None, selected_vac=None):
    """MOSFET loss and junction temperature against the GATE RESISTOR.

    The one number in this chapter the designer picks freely, and the one that moves switching
    loss most. Now that K_Rg is read off the datasheet's own E-vs-Rg curve rather than assumed,
    the sweep is a real re-run of the engine at each value - the same treatment the bridge
    current-sharing sweep gets - so it picks up the de-bundling and the thermal iteration exactly
    as the headline number does.

    Both gate paths are moved together here: the point is the SENSITIVITY, not a specific
    asymmetric design, and the design's own operating point is marked so the reviewer can see how
    much headroom the choice has.
    """
    be = _get_backend(backend)
    import copy
    rg_values = list(rg_values or [1.8, 2.7, 4.7, 6.8, 10.0, 15.0, 22.0])
    vac = float(selected_vac or cfg.get("run", {}).get("vac_list", [90])[0])
    now_on = cfg.get("mosfet", {}).get("rg_on") or cfg.get("mosfet", {}).get("rg")
    p_fet, tj = [], []
    for rg in rg_values:
        c2 = copy.deepcopy(cfg)
        c2.setdefault("mosfet", {}).update({"rg": rg, "rg_on": rg, "rg_off": rg})
        sp, mos, dio, br, th = be.design_from_dict(c2)
        r = be.simulate_point(vac, sp, mos, dio, br, th)
        p_fet.append(r["P_FET_total"] + r.get("P_gate_driver", 0.0))
        tj.append(r["Tj_FET"])
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(rg_values, p_fet, "o-", color=_C["fet"], lw=2, label="MOSFET loss")
    ax.set_xlabel("Gate resistance Rg,on = Rg,off [ohm]"); ax.set_ylabel("MOSFET loss [W]")
    ax.grid(True, alpha=0.3)
    ax2 = ax.twinx()
    ax2.plot(rg_values, tj, "s--", color=_C["accent"], label="Tj FET")
    ax2.set_ylabel("Tj FET [C]")
    if now_on:
        ax.axvline(float(now_on), color=_C["total"], ls=":", lw=1.5)
        ax.annotate(f"this design, {float(now_on):g} ohm", (float(now_on), max(p_fet)),
                    textcoords="offset points", xytext=(6, -14), fontsize=9, color=_C["total"])
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    ax.set_title(f"MOSFET loss and Tj vs gate resistance, at {vac:.0f} Vac")
    return _finish(fig, path, show)


def plot_loss_vs_load(cfg, path, show=False, backend=None, fractions=None, selected_vac=None):
    """Loss and its share of the output against LOAD, at a fixed line voltage.

    Every other figure sweeps line voltage at full power. Efficiency is normally specified across
    the load range, and light load is where the fixed terms - E_oss, gate drive, the diode's
    capacitive charge - stop being negligible against a conduction loss that falls with the square
    of current. That crossover is invisible in a full-load-only chapter, and it is usually where a
    supply misses its efficiency target.

    BOTH the power AND the input-current curve are scaled. `simulate_point` takes `iin_rms_curve`
    in preference to deriving current from power (see its precedence rules), so scaling the power
    alone would have produced full-load currents at part-load power - a plot that looked reasonable
    and was wrong.
    """
    be = _get_backend(backend)
    import copy
    fractions = list(fractions or [0.10, 0.25, 0.50, 0.75, 1.00])
    vac = float(selected_vac or cfg.get("run", {}).get("vac_list", [90])[0])
    spec = cfg.get("spec", {}) or {}

    def _at(curve_or_none, scalar_key):
        if curve_or_none:
            xs, ys = curve_or_none
            return float(np.interp(vac, xs, ys))
        return float(spec.get(scalar_key) or 0.0)

    p_full = _at(spec.get("po_curve"), "po")
    if p_full <= 0:
        raise ValueError("no output power in cfg['spec'] to scale")

    pw, semi, share = [], [], []
    for fr in fractions:
        c2 = copy.deepcopy(cfg)
        sp2 = c2.setdefault("spec", {})
        for key in ("po_curve", "iin_rms_curve", "pin_curve"):
            if sp2.get(key):
                xs, ys = sp2[key]
                sp2[key] = [list(xs), [y * fr for y in ys]]
        for key in ("po", "iin_rms", "pin"):
            if sp2.get(key):
                sp2[key] = float(sp2[key]) * fr
        sp, mos, dio, br, th = be.design_from_dict(c2)
        r = be.simulate_point(vac, sp, mos, dio, br, th)
        po = p_full * fr
        pw.append(po)
        semi.append(r["P_SEMI_total"])
        share.append(100.0 * r["P_SEMI_total"] / po if po else 0.0)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(pw, semi, "o-", color=_C["total"], lw=2, label="Semiconductor loss")
    ax.set_xlabel("Output power [W]"); ax.set_ylabel("Semiconductor loss [W]")
    ax.grid(True, alpha=0.3)
    ax2 = ax.twinx()
    ax2.plot(pw, share, "s--", color=_C["fet"], label="Loss as % of output")
    ax2.set_ylabel("Semiconductor loss / output power [%]")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="center right", fontsize=9)
    ax.set_title(f"Semiconductor loss vs load, at {vac:.0f} Vac")
    return _finish(fig, path, show)


def plot_debundling(mosfet_block, path, show=False):
    """What convention B actually removes from the published turn-on energy.

    This is the least intuitive step in the chapter: the datasheet says E_on = 35 uJ and the model
    uses about 12.6 uJ of it. Stated in prose it invites the reaction that loss is being discarded.
    Drawn, the argument is immediate - a constant is subtracted, not a fraction, because what comes
    off is set by the test VOLTAGE (the device's own C_oss and the fixture's freewheeling charge)
    and is booked separately in Sections 7.4.3 and 7.4.4.

    The remainder falling to about zero at zero current is the evidence that the subtraction is the
    right size: overlap energy is proportional to current, so it MUST vanish there. That is the one
    line on this plot a reviewer should check.
    """
    esw = (mosfet_block or {}).get("_esw_basis") or {}
    if not esw.get("ok"):
        raise ValueError("no measured switching-energy basis on this block")
    eon = mosfet_block.get("eon_curve")
    if not eon:
        raise ValueError("no eon_curve on this block")
    i = np.asarray(eon[0], dtype=float)
    # the block's curve is de-bundled AND K_Rg-scaled; undo the scale to recover what the
    # datasheet published, so the two lines are directly comparable
    k = float(esw.get("k_rg_on") or 1.0) or 1.0
    overlap = np.asarray(eon[1], dtype=float) / k
    sub = float(esw.get("debundled_J") or 0.0)
    published = overlap + sub

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(i, published * 1e6, "o-", color=_C["total"], ms=3, lw=1.8,
            label="published E$_{on}$ (datasheet plot)")
    ax.plot(i, overlap * 1e6, "s-", color=_C["fet"], ms=3, lw=2,
            label="device overlap, used by the model")
    ax.fill_between(i, overlap * 1e6, published * 1e6, color=_C["accent"], alpha=0.25,
                    label=f"removed: {sub*1e6:.1f} uJ, counted in 7.4.3 and 7.4.4")
    it = float(esw.get("i_test") or 0.0)
    if it:
        ax.axvline(it, color=_C["diode"], ls=":", lw=1.4)
        ax.annotate(f"datasheet test point {it:.1f} A", (it, float(published.max() * 1e6)),
                    textcoords="offset points", xytext=(6, -12), fontsize=9, color=_C["diode"])
    resid = float(esw.get("residual_at_min_current_J") or 0.0) * 1e6
    ax.annotate(f"remainder at the lowest plotted current: {resid:+.2f} uJ; overlap is "
                f"proportional to current, so it must fall to about zero",
                (float(i.min()), float(overlap.min() * 1e6)), textcoords="offset points",
                xytext=(10, 26), fontsize=8.5, color=_C["fet"])
    ax.set_xlabel("Drain current at the switching instant [A]")
    ax.set_ylabel("Turn-on energy [uJ]")
    ax.set_title("Published turn-on energy vs the device overlap the model uses")
    ax.grid(True, alpha=0.3); ax.legend(fontsize=9, loc="upper left")
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
