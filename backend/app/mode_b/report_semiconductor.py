"""
Chapter 7 — Semiconductor Loss & Thermal (report)
=================================================
Builds the Chapter-7 PDF from the SAME engine + adapter the GUI uses, so the documented
numbers are identical to the page. Losses are reported at EVERY input voltage (all 9
operating points), then rolled up to the worst-case total and reconciled against the
system loss implied by the design efficiency.

Standalone document (like the Chapter-6 control report) — merged after Chapters 1–6.
"""
from __future__ import annotations
import io, os, tempfile

from app.mode_b.doc_report_builder import (
    chapter_splash, step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.semiconductor.adapter import (
    calculate_semiconductor_losses, build_semi_cfg, build_design_ops, trace_point,
)

_OHM = "&#937;"; _MU = "&#181;"; _DEG = "&#176;"

CH = 7
_TITLE = "Semiconductor Loss & Thermal Design"


def _img_path(path, width=CW):
    # read the PNG into memory NOW (the temp dir is removed before the doc is built)
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    with open(path, "rb") as f:
        data = f.read()
    iw, ih = ImageReader(io.BytesIO(data)).getSize()
    return Image(io.BytesIO(data), width=width, height=ih * (width / iw))


def _f(x, n=2):
    return f"{float(x):.{n}f}"


# Which figure backs which quantity, and what a reviewer should look for in it. Keyed by the
# canonical parameter, so a datasheet that publishes a plot we do not consume never appears and a
# curve we DO consume is never shown without saying what it is for.
_FIGURE_PURPOSE = {
    "V_F_vs_IF":     ("Forward voltage V<sub>F</sub>(I<sub>F</sub>)",
                      "conduction loss is integrated along this curve, not taken at one drop"),
    "V_F_vs_IF_hot": ("Forward voltage at the hot junction",
                      "the second temperature the per-point V<sub>F</sub> interpolates towards"),
    "Q_c_vs_VR":     ("Capacitive charge Q<sub>c</sub>(V<sub>R</sub>)",
                      "read at the bus voltage; booked to the MOSFET in Section 7.4.4"),
    "E_c_vs_VR":     ("Capacitive energy E<sub>c</sub>(V<sub>R</sub>)",
                      "the same commutation energy expressed directly as energy"),
    "C_j_vs_VR":     ("Junction capacitance C<sub>j</sub>(V<sub>R</sub>)",
                      "fits the grading coefficient across the whole plotted range"),
    "I_rev_vs_VR":   ("Reverse current I<sub>R</sub>(V<sub>R</sub>)", "blocking (leakage) loss"),
    "I_F_AV_vs_Tc":  ("Rectified current vs case temperature",
                      "the derating gate of Table 7.3.3 — against CASE, not free air"),
    "E_oss_vs_VDS":  ("Output-capacitance energy E<sub>oss</sub>(V<sub>DS</sub>)",
                      "evaluated at the actual bus, not at the datasheet's 400 V"),
    "C_rss_vs_VDS":  ("Reverse-transfer capacitance C<sub>rss</sub>(V<sub>DS</sub>)",
                      "the Miller integral is taken from this curve instead of Q<sub>gd</sub>V/2"),
    "R_DS_on_vs_Tj": ("On-resistance vs junction temperature",
                      "why a 25&#176;C R<sub>DS(on)</sub> cannot be used; the curve is convex"),
    "R_DS_on_vs_ID": ("On-resistance vs drain current",
                      "normalised, so R<sub>DS(on)</sub> rises with current instead of being flat"),
    "E_on_vs_ID":    ("Turn-on energy vs drain current",
                      "E<sub>on</sub> is read at the inductor VALLEY current at each line angle"),
    "E_off_vs_ID":   ("Turn-off energy vs drain current",
                      "E<sub>off</sub> is read at the PEAK current at each line angle"),
    "E_on_vs_Rg":    ("Turn-on energy vs gate resistance",
                      "supplies K<sub>Rg,on</sub>; the published energies hold only at the "
                      "fixture's resistor"),
    "E_off_vs_Rg":   ("Turn-off energy vs gate resistance",
                      "supplies K<sub>Rg,off</sub>, corrected independently of turn-on"),
}


from app.mode_b.semiconductor.manifest import PROVENANCE_KEY as _PROV_KEY


def _basis(story, block, keys, read_off=None, ch=CH):
    """The EVIDENCE for one loss mechanism, placed with the mechanism that consumes it.

    A worked derivation states a number; this states where the number came from, and it belongs
    beside the equation rather than in a panel four pages later. The rule the designer set:

      * value read off a PLOT  -> show the plot, then say what was read, at which operating point,
        what it gave, and which equation takes it;
      * value from a TABLE     -> say so in one line and show NO plot. A figure that adds nothing
        costs a page and teaches a reviewer to skim past figures that do matter.

    `keys` are the canonical parameters this mechanism consumes, in the order they should appear.
    `read_off` optionally maps a key to a sentence naming the value actually taken at the design's
    operating point — the link that turns a picture into evidence.
    """
    figs = {f["key"]: f for f in ((block or {}).get("_figure_images") or []) if f.get("path")}
    prov = (block or {}).get(_PROV_KEY) or {}
    shown: set = set()
    for key in keys:
        what, why = _FIGURE_PURPOSE.get(key, (key, "used by this calculation"))
        f = figs.get(key)
        note = (read_off or {}).get(key)
        if f:
            # one plot can carry several quantities (E_on and E_off share a figure); print it once
            ident = (f.get("page"), tuple(f.get("frame") or ()) or f["path"])
            if ident not in shown:
                shown.add(ident)
                try:
                    story.append(_img_path(f["path"], width=CW * 0.52))
                except Exception:
                    pass
            src = (f"{f['figure']}, page {f['page']}" if f.get("figure")
                   else (f"page {f['page']}" if f.get("page") else "the datasheet"))
            _W(story, f"<b>{what}</b> &#8212; read from {src}. {note or (why + '.')}")
        elif prov.get(key) in ("extracted", "corrected"):
            _W(story, f"<b>{what}</b> &#8212; taken from the datasheet's parameter TABLE, not a "
                      f"plot; no figure is shown because there is none to read. "
                      + (note or f"{why.capitalize()}."))
        elif prov.get(key) == "derived":
            _W(story, f"<b>{what}</b> &#8212; DERIVED, not published. "
                      + (note or f"{why.capitalize()}."))


_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "semiconductor", "assets")

def _config_schematic(topology, n_parallel):
    """(Image, caption) for the selected bridge configuration; (None, None) if asset missing."""
    if topology == "sync_bottom":
        name, cap = ("schematic_3_dual_bridge_bypass_mosfets.png",
                     "Dual split bridges with bypass MOSFETs on the bottom legs: each package's AC "
                     "pins are shorted (one package per line conductor), the top arms are the "
                     "paralleled diode pairs, and Q1/Q2 bypass the bottom return path at line "
                     "frequency. Q1 and Q2 must never be enhanced simultaneously (L–N short).")
    elif int(n_parallel or 1) >= 2:
        name, cap = ("schematic_2_dual_bridge_parallel_diodes.png",
                     "Dual split-bridge arrangement: each package's two AC pins are shorted (BR1 on "
                     "Neutral, BR2 on Line), so every conduction arm is a matched diode pair inside "
                     "one package and each package permanently dissipates one arm's loss.")
    else:
        name, cap = ("schematic_1_single_bridge.png",
                     "Conventional single full-bridge rectifier: two diodes in series conduct at "
                     "every instant; all bridge loss is concentrated in one package.")
    path = os.path.join(_ASSETS, name)
    if not os.path.exists(path):
        return None, None
    return _img_path(path, width=CW * 0.72), cap


def _uj(x):
    return f"{float(x) * 1e6:.2f} {_MU}J"


def _nc(x):
    return f"{float(x) * 1e9:.0f} nC"


# ── narrative worked calculations (model → equation → worked at 90 V and 180 V) ─────────
# These follow the style of the earlier chapters: each loss has a short explanation of the
# model and why it is used, the governing equation, then the substituted numbers at each corner.
def _W(story, txt):
    body(story, txt, CH)


def _worked(story, num, title, step_rows, traces, ch=CH):
    """Render a step-by-step worked derivation as a table — one column per worst-case corner
    (low line + high line), each row a step (equation → enter values → result) that shows how the
    9-point summary Table value is derived. `step_rows` is a list of (label, cell_fn) where
    cell_fn(tr) returns the substituted-and-solved string for that corner."""
    if not traces:
        return
    def _corner(v):
        return ("Low line" if v < 180 else "High line") + f" &mdash; {v:.0f} V<sub>AC</sub>"
    headers = ["Step (equation → substitution → result)"] + [_corner(v) for v, _ in traces]
    rows = [[lbl] + [fn(tr) for _, tr in traces] for lbl, fn in step_rows]
    n = max(len(traces), 1)
    col_widths = [CW * 0.30] + [CW * (0.70 / n)] * n
    data_table(story, num, title,
               "Worst-case worked substitution behind the Table values — one column per line corner.",
               headers, rows, col_widths, ch=ch)


def _sharing_sweep(design, mosfet, diode, bridge, thermal):
    """Bridge loss at 50/50, 60/40, 70/30 and single-path sharing.

    Paralleled rectifiers do not share equally: the hotter package takes more current, and its own
    loss makes it hotter. The nominal number assumes they split evenly, which is the assumption a
    reviewer most wants to see tested — so the alternatives are computed rather than asserted.

    It is a genuine sweep, not a formula: each case re-runs the engine with the derate applied, so
    it picks up the V-I curve and the thermal iteration exactly as the headline number does.
    """
    from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
    import copy

    n_par = int((bridge or {}).get("n_parallel") or 1)
    if n_par < 2:
        return None
    out = []
    for label, k in (("50 / 50 (ideal)", 0.5), ("60 / 40", 0.6),
                     ("70 / 30", 0.7), ("single path", 1.0)):
        b = copy.deepcopy(bridge)
        if k >= 1.0:
            b["n_parallel"] = 1
            b.pop("share_worst", None)
        else:
            b["share_worst"] = k
        try:
            res = calculate_semiconductor_losses(design, mosfet, diode, b, thermal, None)
            rows = res["per_point"]
            if not rows:
                continue
            worst = max(rows, key=lambda r: r["P_BRIDGE_total"])
            out.append({"case": label, "P": worst["P_BRIDGE_total"],
                        "Tj": worst["Tj_BRIDGE_top"], "Vac": worst["Vac"]})
        except Exception:
            continue
    return out or None


def _derating_check(design, bridge, worst_row, thermal=None):
    """Is the part ALLOWED to carry this current at the case temperature it will run at?

    Section 7.3 has described this gate since C218 without computing it. A room-temperature I_F(AV)
    rating does not answer it: the LVE5060E is a 50 A bridge at 50 degC case and a 21 A bridge at
    140 degC, and the operating point that matters sits between them. The loss calculation is
    unaffected either way - this is a PERMISSION check, and a part can be thermally fine on its own
    junction temperature while being operated outside what the vendor allows.

    The current compared is the one the REQUIREMENT already derived (`I_per_package`), not a second
    derivation of the same quantity. Two expressions for one number is how they come to disagree.

    Returns None when the design has no bridge to check; a DATA MISSING verdict when the curve has
    not been digitised, because an ungated part must not read as a passing one.
    """
    from app.mode_b.semiconductor import curve_extract as CX
    from app.mode_b.semiconductor.datasheet_flow import requirements

    if not bridge or not worst_row:
        return None
    n_par = max(int((bridge or {}).get("n_parallel") or 1), 1)
    curve = (bridge or {}).get("_i_f_av_vs_tc")

    try:
        # n_parallel comes from the BLOCK, which is what the engine actually ran, and is fed back
        # into the requirement so the per-package figure has ONE derivation. Calling it with the
        # bare design compared the TOTAL rectified current against a PER-PACKAGE allowance, which
        # overstated the draw by the number of packages.
        actual = float(requirements({**design, "n_parallel": n_par}, "bridge")["I_per_package"])
    except Exception:
        return None

    p_pkg = float(worst_row.get("P_BRIDGE_top") or 0.0) / n_par
    t_j = worst_row.get("Tj_BRIDGE_top")
    rth_jc = float((bridge or {}).get("rth_jc") or 0.0)
    # T_case from the junction the engine solved for, back down the SAME junction-to-case path the
    # engine used. Deriving it from the sink instead would be a second thermal model.
    t_case = (float(t_j) - p_pkg * rth_jc) if t_j is not None else None

    out = {"I_allowed_A": None, "I_actual_A": round(actual, 2), "T_case_C": None,
           "n_parallel": n_par, "P_per_package_W": round(p_pkg, 2),
           "Vac": worst_row.get("Vac")}
    if t_case is not None:
        out["T_case_C"] = round(t_case, 1)

    if not curve or not curve[0]:
        out["verdict"] = "DATA MISSING"
        out["statement"] = (
            "The derating curve has not been read from the datasheet, so whether the part is "
            "permitted to carry {:.1f} A at {} is UNKNOWN. Confirm the curve of allowed average "
            "rectified current against CASE temperature on the Curves tab.".format(
                actual, "{:.0f}°C case".format(t_case) if t_case is not None
                else "its operating temperature"))
        return out

    pts = {"x": list(curve[0]), "y": list(curve[1])}
    allowed = CX.value_at(pts, t_case) if t_case is not None else None
    if allowed is None:
        # Off the end of the published curve. Beyond its last point the part is not rated at all,
        # which is a FAIL and not a missing number.
        t_max = max(pts["x"]) if pts["x"] else None
        out["verdict"] = "FAIL" if (t_case is not None and t_max is not None
                                    and t_case > t_max) else "DATA MISSING"
        out["T_curve_max_C"] = round(t_max, 1) if t_max is not None else None
        out["statement"] = (
            "The case temperature {:.0f}°C is beyond the end of the published derating "
            "curve ({:.0f}°C), where the part carries no rating at all.".format(t_case, t_max)
            if out["verdict"] == "FAIL" else
            "The derating curve could not be read at the operating case temperature.")
        return out

    out["I_allowed_A"] = round(allowed, 2)
    out["headroom_pct"] = round((allowed - actual) / actual * 100.0, 1) if actual else None
    out["verdict"] = "PASS" if allowed >= actual else "FAIL"
    out["statement"] = (
        "At {:.0f}°C case the datasheet allows {:.1f} A average rectified current per "
        "package; "
        "the design draws {:.1f} A across {} package(s). {}".format(
            t_case, allowed, actual, n_par,
            "Permitted, with {:.0f} % headroom.".format(out["headroom_pct"])
            if out["verdict"] == "PASS" else
            "NOT permitted - the part is being operated outside its derating curve."))
    return out


def _bridge_section(story, traces, is_sync, bridge=None, sharing=None, derating=None):
    _W(story,
       "<b>Model.</b> The bridge rectifies the AC line; at every instant two devices in series carry "
       "the full rectified current i<sub>in</sub>(&#952;) = &#8730;2&#183;I<sub>in,rms</sub>&#183;sin&#952;. "
       "A diode's forward-drop conduction loss is V<sub>f</sub> times its <b>average</b> current (the "
       "V<sub>f</sub>&#183;i product integrates to V<sub>f</sub>&#183;I<sub>avg</sub> for a fixed "
       "V<sub>f</sub>) — <i>not</i> I<sub>rms</sub>, which would only apply to an ohmic "
       "R<sub>d</sub>&#183;i&#178; term. Because V<sub>f</sub>(i) is itself current-dependent (read from "
       "the datasheet V-I curve, well above the textbook 0.7 V at tens of amps), we integrate the exact "
       "V<sub>f</sub>(i)&#183;i product over the half cycle rather than using a single point, and double "
       "it for the conducting pair." +
       (" For the sync-bottom variant the bottom legs are MOSFETs, adding an ohmic "
        "R<sub>ds</sub>&#183;I<sub>rms</sub>&#178; term (resistive, so RMS-based) and a small "
        "line-frequency gate loss." if is_sync else ""))
    eq_box(story, [r"i_{in}(\theta)=\sqrt{2}\,I_{in,rms}\,\sin\theta,\qquad "
                   r"I_{in,avg}=\frac{2}{\pi}\,\hat{i}_{in}=\frac{2\sqrt{2}}{\pi}\,I_{in,rms}",
                   r"P_{bridge}=2\,\overline{\,V_f(i_{in})\,i_{in}\,}\;\approx\;2\,V_f\,I_{in,avg}"
                   + (r"+\,\overline{\,R_{ds,bot}\,i_{in}^2\,}+P_{g,bot}" if is_sync else "")],
           number="7.3", ch=CH)
    def _iavg(tr):
        return (2.0 / 3.141592653589793) * (2 ** 0.5) * tr["Iin_rms"]
    steps = [
        ("I<sub>in,rms</sub> (from Section 7.1)", lambda tr: f"{_f(tr['Iin_rms'],3)} A"),
        ("I<sub>in,avg</sub> = (2&#8730;2/&#960;)&#183;I<sub>in,rms</sub>",
         lambda tr: f"(2&#8730;2/&#960;)&#215;{_f(tr['Iin_rms'],3)} = {_f(_iavg(tr),3)} A"),
        ("V<sub>f</sub>(i) along the curve",
         lambda tr: f"&#8776; {_f(tr['vf_br_pk'],3)} V (T<sub>j</sub>={_f(tr['Tj_brT'],0)}{_DEG}C)"),
        ("P<sub>bridge</sub> = 2&#183;avg[V<sub>f</sub>(i)&#183;i] (pair)",
         lambda tr: f"<b>{_f(tr['P_bridge'])} W</b>"),
    ]
    if is_sync:
        # The bottom-diode crest share exists only where the crest current pushes the sync-MOSFET
        # channel drop above the bridge-diode knee (low line). Show it on EVERY column when any point
        # has it, so a high-line "+ 0.00 W" reads as an intentional zero, not a missing term.
        _show_bd = any(float(t.get('P_bridge_bd_share', 0) or 0) > 0.05 for _, t in traces)
        steps.append(("&nbsp;&nbsp;split: top diodes / bottom MOSFETs"
                      + ("&nbsp;(+ bottom-diode crest share)" if _show_bd else ""),
                      lambda tr: (f"{_f(tr['P_bridge_top'])} W / {_f(tr['P_bridge_bottom'])} W"
                                  + (f" + {_f(float(tr.get('P_bridge_bd_share', 0) or 0))} W" if _show_bd else ""))))
    # 7.3a, not 7.3.1: Section 7.3.1 is the surge-withstand check and owns a table of that
    # number. Both render whenever the bridge datasheet publishes I_FSM and I2t, which a real
    # one does — so the clash was invisible with catalogue parts and appeared the moment a
    # vendor PDF was used. Lettered suffixes are how tables under a section are already named
    # here (7.2a-7.2e).
    _worked(story, "7.3a", "Bridge Loss — Worked Derivation", steps, traces)
    _btr = traces[0][1] if traces else {}
    _basis(story, bridge, ["V_F_vs_IF", "V_F_vs_IF_hot"], {
        "V_F_vs_IF": (
            f"The per-diode forward drop is integrated along this curve at the instantaneous "
            f"rectified current, not taken at a single point &#8212; which is also why no separate "
            f"dynamic resistance r<sub>d</sub> is added: the slope is already in the curve. At "
            f"{_f(_btr.get('Iin_rms', 0), 1)} A<sub>rms</sub> and the converged "
            f"T<sub>j</sub> = {_f(_btr.get('Tj_brT', 0), 0)}{_DEG}C it gives the drop used above."),
        "V_F_vs_IF_hot": (
            "The hot curve the per-point drop interpolates towards; a rectifier's forward voltage "
            "FALLS with temperature, so using the 25&#176;C curve alone overstates the loss."),
    })

    _b = bridge or {}
    _est = list(_b.get("_estimated") or [])
    _src = _b.get("_source") or ""
    if _b.get("part_number"):
        annotation(story, "BRIDGE PART",
            f"<b>{_b.get('manufacturer') or ''} {_b['part_number']}</b>. "
            + (f"Its model parameters come from {_src}. " if _src else "")
            + ("Every one of them is datasheet-backed."
               if not _est else
               f"Estimated by the engine rather than read: {', '.join(str(e) for e in _est)}."),
            CH)

    _rths = _b.get("_rth_jc_published")
    if _rths and len(_rths) > 1:
        annotation(story, "THERMAL",
            f"The datasheet publishes more than one junction-to-case resistance "
            f"({', '.join(f'{r:g}' for r in _rths)} K/W). The LARGEST is used, because that is the "
            f"per-die figure the junction actually sees; a smaller one describes the whole package "
            f"and would halve the predicted rise.", CH)

    if sharing:
        rows = [[c["case"], f"{_f(c['P'])} W", f"{_f(c['Tj'],1)}{_DEG}C", f"{_f(c['Vac'],0)} V<sub>AC</sub>"]
                for c in sharing]
        # Only the SHARING cases. The single-path fallback is a different circuit — one package
        # carrying everything — so it legitimately differs and including it hides the very thing
        # this is testing for.
        shared = [c["P"] for c in sharing if "single" not in c["case"]]
        collapsed = len(shared) > 1 and (max(shared) - min(shared)) < 0.05
        data_table(story, "7.3.2", "Bridge Current-Sharing Sensitivity",
            "Paralleled rectifiers do not share equally — the hotter package takes more current, "
            "and its own loss makes it hotter. The nominal figure assumes an even split, so the "
            "alternatives are computed here rather than asserted. Each case re-runs the engine with "
            "the derate applied, so it carries the same V-I curve and thermal iteration as the "
            "headline number." + (
                "<br/><br/><b>These cases are currently indistinguishable, and that is a statement "
                "about the DATA rather than about the hardware.</b> The forward drop is being taken "
                "from a single tabulated point, which makes V<sub>f</sub>(i) a constant — and a "
                "constant drop gives the same loss however the current divides, because the derate "
                "cancels. Digitising the datasheet's forward-characteristic curve is what makes "
                "this table mean anything."
                if collapsed else ""),
            ["Sharing case", "Worst-case bridge loss", "T<sub>j</sub>", "at"],
            rows, col_widths=[CW*0.28, CW*0.26, CW*0.20, CW*0.26], ch=CH)

    if derating:
        v = derating.get("verdict")
        drows = [
            ["Case temperature at the worst point",
             f"{_f(derating.get('T_case_C'), 1)}{_DEG}C"],
            ["Average rectified current per package",
             f"{_f(derating.get('I_actual_A'), 2)} A"],
            ["Allowed at that case temperature",
             (f"{_f(derating.get('I_allowed_A'), 2)} A" if derating.get("I_allowed_A") is not None
              else "&#8212; not read")],
            ["Headroom",
             (f"{_f(derating.get('headroom_pct'), 0)} %" if derating.get("headroom_pct") is not None
              else "&#8212;")],
            ["Verdict", f"<b>{v}</b>"],
        ]
        _basis(story, bridge, ["I_F_AV_vs_Tc"], {
            "I_F_AV_vs_Tc": (
                "The allowed average rectified current is read off this curve at the case "
                "temperature the thermal solve converged to &#8212; matched on CASE temperature "
                "specifically, because vendors print a free-air curve beside it rated several "
                "times lower. That reading is the limit in the check below."),
        })
        data_table(story, "7.3.3", "Bridge Derating Check",
            "A room-temperature I<sub>F(AV)</sub> rating does not say whether the part may carry "
            "this current at the temperature it actually runs at, and the two answers diverge "
            "sharply &#8212; every rectifier's allowed current falls away above its knee and "
            "reaches zero at its maximum rated case temperature. The values below are read from "
            "this part's own published curve. The loss calculation is unaffected either way "
            "&#8212; this is a "
            "PERMISSION check, and a device can sit comfortably inside its junction-temperature "
            "limit while being operated outside what the vendor allows. The current compared is "
            "the same per-package figure the sourcing requirement derived, not a second "
            "derivation of it; the case temperature comes back down the same junction-to-case "
            "path the loss model used.",
            ["Quantity", "Value"], drows,
            col_widths=[CW*0.62, CW*0.38], ch=CH)
        annotation(story, "DERATING", derating.get("statement") or "")

    _surge = [k for k in ("ifsm_A", "i2t_A2s") if _b.get(k) not in (None, "")]
    if _surge or _b.get("_provenance", {}).get("I_FSM") or _b.get("_provenance", {}).get("I2t"):
        annotation(story, "SURGE ONLY",
            "I<sub>FSM</sub> and I&#178;t are read from the bridge datasheet and used ONLY for the "
            "cold-start inrush and fuse-coordination checks in Chapter 8. They take no part in "
            "steady-state conduction loss, and are named here so their absence from the loss table "
            "reads as deliberate rather than as an oversight.", CH)



def _mosfet_section(story, traces, mosfet=None, diode=None):
    # `diode` is here for Section 7.4.4 alone: the charge dumped into the FET at turn-on is
    # the DIODE's, so the plot that evidences it comes off the diode's datasheet even though
    # the energy is dissipated in the MOSFET and booked to it.
    nch = int(traces[0][1]["Nch"]) if traces else 1
    # the recovery split the model ACTUALLY used, not a figure typed into the prose
    _frac = float(traces[0][1].get("rr_fet_frac", 0.85)) if traces else 0.85

    sub_h(story, "7.4.1", "Conduction loss", CH)
    _W(story,
       "<b>Model.</b> While the MOSFET is on it is a resistor R<sub>ds(on)</sub>, so the loss is the "
       "on-state RMS current squared times that resistance. The on-state RMS current is the "
       "<i>duty-weighted</i> integral of the channel current over the line cycle (the FET conducts only "
       "during the on-time d). R<sub>ds(on)</sub> has a strong positive temperature coefficient "
       "(&#8776; +0.4&#8211;0.5 %/&#176;C for SiC), so we evaluate it at the converged hot junction "
       "temperature — a 25&#176;C value would under-state the loss by 20&#8211;40 %.")
    # WHAT i^2 IS, WRITTEN OUT. The compact form was read by an external reviewer as possibly the
    # square of the AVERAGE channel current, which would drop the ripple contribution entirely.
    # The engine evaluates the switching-cycle triangular mean square, and these are identical:
    # [(i-di/2)^2 + (i-di/2)(i+di/2) + (i+di/2)^2]/3 = i^2 + di^2/12.
    eq_box(story, [r"I_{FET,rms}=\sqrt{\overline{\,i^2\,d\,}},\qquad R_{ds(on)}(T_j)=R_{ds,25}\,k(T_j)",
                   r"i^2(\theta)=\frac{I_{valley}^2+I_{valley}I_{peak}+I_{peak}^2}{3}"
                   r"=I_{ch}^2(\theta)+\frac{\Delta I_L^2(\theta)}{12}",
                   r"P_{cond}=N_{ch}\,R_{ds(on)}(T_j)\,I_{FET,rms}^2"], number="7.4.1", ch=CH)
    _W(story,
       "The middle line is the point a reviewer should check: <b>i&#178; is the switching-cycle "
       "<i>triangular</i> mean square</b>, not the square of the average channel current. The two "
       "forms shown are algebraically identical &#8212; the engine evaluates the right-hand one "
       "&#8212; and using the average instead would discard the ripple term "
       "&#916;I<sub>L</sub>&#178;/12, which is not negligible at low line. The duty factor d gates "
       "it to the MOSFET on-time; in DCM the same integral is taken over the actual conduction "
       "sub-interval instead.")
    _worked(story, "7.4.1", "Conduction Loss — Worked Derivation", [
        ("R<sub>ds(on)</sub>(T<sub>j</sub>) = R<sub>ds,25</sub>&#183;k(T<sub>j</sub>)",
         lambda tr: f"{_f(tr['rds_25']*1e3,1)}m&#215;{_f(tr['rds_tj_factor'],3)} (T<sub>j</sub>={_f(tr['Tj_fet'],0)}{_DEG}C) = {_f(tr['rds_tj']*1e3,1)} m{_OHM}"),
        ("I<sub>FET,rms</sub> = &#8730;(avg[i&#178;d])", lambda tr: f"{_f(tr['i_fet_rms_ch'],3)} A"),
        ("P<sub>cond</sub> = N<sub>ch</sub>&#183;R<sub>ds(on)</sub>&#183;I<sub>FET,rms</sub>&#178;",
         lambda tr: f"{nch}&#215;{_f(tr['rds_tj']*1e3,1)}m&#215;({_f(tr['i_fet_rms_ch'],3)})&#178; = <b>{_f(tr['P_cond_fet_tot'])} W</b>"),
    ], traces)
    _tr0 = traces[0][1] if traces else {}
    _basis(story, mosfet, ["R_DS_on", "R_DS_on_vs_Tj", "R_DS_on_vs_ID"], {
        "R_DS_on": (f"The 25&#176;C value the curve is anchored on is "
                    f"{_f(_tr0.get('rds_25', 0)*1e3, 1)} m{_OHM}."),
        "R_DS_on_vs_Tj": (
            f"Read at the converged junction temperature "
            f"T<sub>j</sub> = {_f(_tr0.get('Tj_fet', 0), 0)}{_DEG}C, giving a factor of "
            f"{_f(_tr0.get('rds_tj_factor', 0), 3)} and "
            f"R<sub>DS(on)</sub> = {_f(_tr0.get('rds_tj', 0)*1e3, 1)} m{_OHM} &#8212; the value "
            f"entering P<sub>cond</sub> in the derivation above."),
        "R_DS_on_vs_ID": (
            "Normalised on the current the parameter table states, so it contributes the SHAPE of "
            "the rise with drain current while the table supplies the level."),
    })

    sub_h(story, "7.4.2", "Switching loss (turn-on + turn-off)", CH)
    # WHICH MODEL IS ACTUALLY RUNNING DECIDES WHAT THIS SECTION SAYS. When a measured E(I_D) curve
    # has been confirmed the engine switches to it, and a section still describing the analytic
    # crossover model would be documenting a calculation that did not happen.
    _esw = (mosfet or {}).get("_esw_basis") or {}
    _use_curves = (mosfet or {}).get("sw_method") == "esw" and _esw.get("ok")
    if _use_curves:
        _W(story,
           "<b>Model.</b> Turn-on and turn-off energy are taken from the <b>datasheet's own "
           "measured E(I<sub>D</sub>) curves</b>, not from an analytic crossover model. Each is "
           "evaluated at the current that actually flows at that instant &#8212; E<sub>on</sub> at "
           "the inductor <i>valley</i> current, since the channel takes over there, and "
           "E<sub>off</sub> at the <i>peak</i> &#8212; at every angle of the line cycle, so the "
           "energy tracks the current the same way the vendor measured it. Two corrections are "
           "applied and both are shown below: the published turn-on energy is <b>de-bundled</b> "
           "(Table 7.4.2b) because this chapter books E<sub>oss</sub> and the diode charge "
           "separately in Sections 7.4.3 and 7.4.4, and the energies are <b>corrected for this "
           "design's gate resistors</b>, which are not the ones the datasheet was measured at.")
        # mathtext has no \big[ ; plain brackets render and \left[..\right] is the only other form
        eq_box(story, [r"E_{on}(\theta)=[\,E_{on,ds}(i_{valley})-E_{oss}(V_{test})-Q_{fw}V_{test}\,]"
                       r"\,K_{Rg,on}\,\frac{V_{OUT}}{V_{test}}",
                       r"E_{off}(\theta)=E_{off,ds}(i_{peak})\,K_{Rg,off}\,\frac{V_{OUT}}{V_{test}},"
                       r"\qquad P_{sw}=N_{ch}\,f_{sw}\,\overline{E_{on}+E_{off}}"],
               number="7.4.2", ch=CH)
    else:
        _W(story,
           "<b>Model.</b> At hard switching the drain voltage and current overlap during the transition, "
           "dissipating a crossover energy each cycle. Rather than a single datasheet E<sub>sw</sub> figure "
           "(quoted at one R<sub>g</sub>/V<sub>DS</sub>/I that rarely matches the design), we compute "
           "E<sub>on</sub> and E<sub>off</sub> <i>analytically</i> from the actual gate drive: the "
           "current rise/fall times from C<sub>iss</sub>&#183;R<sub>g</sub>&#183;ln(&#183;) and the "
           "Miller-plateau charge J = Q<sub>gd</sub>&#183;V<sub>OUT</sub>/2 (or the C<sub>rss</sub>(V) "
           "integral). This makes E<sub>sw</sub> scale correctly with this design's R<sub>g</sub>, V<sub>g</sub>, "
           "operating current and T<sub>j</sub>. The loss is f<sub>sw</sub> times the cycle-averaged energy.")
        eq_box(story, [r"E_{sw}(i,V_{OUT},T_j)=E_{on}+E_{off},\qquad "
                       r"P_{sw}=N_{ch}\,f_{sw}\,\overline{E_{sw}}"], number="7.4.2", ch=CH)
    _worked(story, "7.4.2", "Switching Loss — Worked Derivation", [
        ("i<sub>on</sub> / i<sub>off</sub> (peak of line)",
         lambda tr: f"{_f(tr['i_on_pk'],2)} / {_f(tr['i_off_pk'],2)} A"),
        ("E<sub>sw</sub> = E<sub>on</sub>+E<sub>off</sub> (peak / cycle-avg)",
         lambda tr: f"{_uj(tr['Esw_pk'])} / {_uj(tr['Esw_avg'])}"),
        ("P<sub>sw</sub> = N<sub>ch</sub>&#183;f<sub>sw</sub>&#183;avg(E<sub>sw</sub>)",
         lambda tr: f"{nch}&#215;{_f(tr['fsw']/1e3,0)}kHz&#215;{_uj(tr['Esw_avg'])} = <b>{_f(tr['P_sw_fet_tot'])} W</b>"),
    ], traces)

    if _use_curves:
        _eo = _esw.get("eoss_test_J") or 0.0
        data_table(story, "7.4.2b", "Measured Switching Energy — Extraction and Corrections",
            "Every number the switching model uses, and what it was checked against. The plot and "
            "the parameter table are independent renderings of one measurement, so their agreement "
            "at the test point is what says the curve was read correctly.",
            ["Quantity", "Value", "Basis"],
            [["E<sub>on</sub> read at test point",
              f"{_esw['error_pct']['E_on']:.2f} % from table",
              f"digitised E(I<sub>D</sub>) curve at {_esw['i_test']:.1f} A"],
             ["E<sub>off</sub> read at test point",
              f"{_esw['error_pct']['E_off']:.2f} % from table",
              f"digitised E(I<sub>D</sub>) curve at {_esw['i_test']:.1f} A"],
             ["&#8722; E<sub>oss</sub>(V<sub>test</sub>)", f"{_eo*1e6:.2f} {_MU}J",
              f"counted separately in Section 7.4.3"],
             ["&#8722; fixture charge Q<sub>fw</sub>&#183;V<sub>test</sub>",
              f"{_esw['q_fw_C']*_esw['v_test']*1e6:.2f} {_MU}J",
              (f"{_esw['q_fw_C']*1e9:.0f} nC "
               + ("stated by the datasheet" if _esw.get("q_fw_stated") else "assumed midpoint")
               + "; counted in Section 7.4.4")],
             ["De-bundled turn-on total", f"&#8722;{_esw['debundled_J']*1e6:.2f} {_MU}J",
              "removed before the curve is used, so no term is counted twice"],
             ["Residual at lowest plotted current",
              f"{_esw['residual_at_min_current_J']*1e6:+.2f} {_MU}J",
              "<b>the check</b>: overlap energy is proportional to current, so it must fall to "
              "about zero here"],
             ["K<sub>Rg,on</sub>", f"{_esw['k_rg_on']:.3f}",
              f"R<sub>g,on</sub> {float(_esw['rg_on'] or 0):g} {_OHM} vs "
              f"{_esw['rg_test']:g} {_OHM} test, from the E vs R<sub>g</sub> curve"],
             ["K<sub>Rg,off</sub>", f"{_esw['k_rg_off']:.3f}",
              f"R<sub>g,off</sub> {float(_esw['rg_off'] or 0):g} {_OHM} vs "
              f"{_esw['rg_test']:g} {_OHM} test, corrected independently of turn-on"]],
            col_widths=[CW*0.34, CW*0.22, CW*0.44], ch=CH)
        annotation(story, "GATE PATH",
            "The published switching energies are valid only at the gate resistor the datasheet "
            "measured them with. The turn-on path sets dv/dt and E<sub>on</sub>; the turn-off path "
            "sets E<sub>off</sub>. They are therefore corrected <b>separately</b> &#8212; using one "
            "figure for both would hide the design intent of an asymmetric gate drive.", CH)
        for _n in (_esw.get("notes") or []):
            annotation(story, "Esw NOTE", _n, CH)
        _basis(story, mosfet, ["E_on_vs_ID", "E_off_vs_ID", "E_on_vs_Rg", "E_off_vs_Rg"], {
            "E_on_vs_ID": (
                f"Turn-on is read at the inductor VALLEY current at each line angle, then "
                f"de-bundled by {_esw['debundled_J']*1e6:.1f} {_MU}J as Table 7.4.2b sets out. At "
                f"the datasheet's own {_esw['i_test']:.1f} A test point the curve agrees with its "
                f"table to {_esw['error_pct']['E_on']:.2f} %."),
            "E_off_vs_ID": (
                f"Turn-off is read at the PEAK current, and is not de-bundled &#8212; no "
                f"C<sub>oss</sub> discharge or recovery charge flows through the device at "
                f"turn-off. Agrees with the table to {_esw['error_pct']['E_off']:.2f} %."),
            "E_on_vs_Rg": (
                f"Supplies K<sub>Rg,on</sub> = {_esw['k_rg_on']:.3f} for the design's "
                f"{float(_esw['rg_on'] or 0):g} {_OHM} turn-on path against the "
                f"{_esw['rg_test']:g} {_OHM} the energies were measured at."),
            "E_off_vs_Rg": (
                f"Supplies K<sub>Rg,off</sub> = {_esw['k_rg_off']:.3f} for the "
                f"{float(_esw['rg_off'] or 0):g} {_OHM} turn-off path, corrected independently of "
                f"turn-on."),
        })

    # M4b. When the switching model is anchored on published energies, the report MUST show the
    # de-bundling arithmetic: the whole basis for keeping a separate E_oss term alongside a
    # datasheet E_on is that the bundled parts were subtracted first. A reader has to be able to
    # check that, not take it on trust.
    _anch = (mosfet or {}).get("_switching_anchor") or {}
    if _anch.get("ok"):
        _b = _anch["basis"]
        annotation(story, "ANCHOR",
            (f"The analytic crossover model is retained as an <b>independent cross-check</b> on the "
             f"measured curves above, not as the reported calculation. It is built from the gate "
             f"drive &#8212; C<sub>iss</sub>, Q<sub>gd</sub>, R<sub>g</sub> &#8212; and so shares no "
             f"input with a digitised plot; the two agreeing is evidence neither could give alone. "
             if _use_curves else
             f"The switching model is <b>anchored on the datasheet's published energies</b> rather "
             f"than run open-loop. ")
            + f"{_anch['statement']}<br/><br/>"
            f"<b>Why the subtraction.</b> A published E<sub>on</sub> is measured in a double-pulse "
            f"fixture and bundles three things: the device's own voltage-current overlap, the "
            f"discharge of its own C<sub>oss</sub>, and the charge of the freewheeling element. "
            f"This chapter counts the last two separately, in Sections 7.4.3 and 7.4.4. Anchoring "
            f"on the raw published figure while keeping those terms would count them twice, so "
            f"they are removed before the anchor is taken. E<sub>off</sub> needs no such treatment "
            f"— no C<sub>oss</sub> discharge or recovery charge flows through the device at "
            f"turn-off — which is what makes it the clean check on the other.", CH)
        _band = _anch.get("band") or {}
        if not _band.get("stated"):
            annotation(story, "ANCHOR BAND",
                f"The datasheet does not state which freewheeling device its switching-energy "
                f"fixture used, so the charge it contributed is not known exactly. The anchor uses "
                f"the midpoint of a {_band.get('q_fw_low_C', 0)*1e9:.0f}&#8211;"
                f"{_band.get('q_fw_high_C', 0)*1e9:.0f} nC range; across that range k<sub>on</sub> "
                f"spans {_band.get('k_on_low', 0):.2f} to {_band.get('k_on_high', 0):.2f}, worth "
                f"about &#177;5% on total MOSFET loss. An independent check &#8212; anchoring on "
                f"E<sub>off</sub>, which carries no bundled charge, and asking what the fixture "
                f"must then have contributed &#8212; gives "
                f"{_anch.get('implied_q_fw_C', 0)*1e9:.0f} nC, inside that range.", CH)
        # 7.4.2c, NOT 7.4.2b: C225 added a "Measured Switching Energy" table under 7.4.2b without
        # noticing this one already held that number, and both render in the same document when
        # the curves are in use. A duplicate table number is invisible to `ast.parse` and to any
        # audit that only asks whether a series starts at 'a' — it shows up solely in a built PDF.
        data_table(story, "7.4.2c", "Switching-Energy Anchor (analytic cross-check)",
            "Both factors are shown because their DIVERGENCE is the diagnostic: a magnitude error "
            "would scale turn-on and turn-off alike, so a large difference after de-bundling points "
            "at the model's shape rather than its size.",
            ["Quantity", "Published", "Model, unscaled", "Anchor factor"],
            [["Turn-on E<sub>on</sub> (de-bundled)",
              f"{(_b['E_on_ds'] - _b['E_oss_at_test'] - (_band.get('q_fw_used_C', 0) * _b['V_test']))*1e6:.1f} {_MU}J",
              f"{_b['E_on_analytic']*1e6:.1f} {_MU}J", f"k<sub>on</sub> = {_anch['k_on']:.2f}"],
             ["Turn-off E<sub>off</sub>", f"{_b['E_off_ds']*1e6:.0f} {_MU}J",
              f"{_b['E_off_analytic']*1e6:.1f} {_MU}J", f"k<sub>off</sub> = {_anch['k_off']:.2f}"],
             ["Test conditions",
              f"{_b['V_test']:.0f} V, {_b['I_test']:.1f} A",
              f"R<sub>g</sub> {_b['R_g_test']:g} {_OHM}, T<sub>j</sub> {_b['T_j_test']:.0f}{_DEG}C",
              "&#8212;"]],
            col_widths=[CW*0.32, CW*0.22, CW*0.22, CW*0.24], ch=CH)
        for _n in (_anch.get("notes") or []):
            if "outside" in _n or "differ by" in _n:
                annotation(story, "ANCHOR CHECK", _n, CH)

    sub_h(story, "7.4.3", "Output-capacitance loss (E<sub>oss</sub>)", CH)
    _W(story,
       "<b>Model.</b> While off, the MOSFET output capacitance C<sub>oss</sub> charges to V<sub>OUT</sub>; "
       "at the next hard turn-on that stored charge is dumped through the channel and dissipated. We use "
       "the datasheet stored energy E<sub>oss</sub>(V<sub>OUT</sub>) — the &#189;&#8747;V dQ integral of "
       "the strongly non-linear C<sub>oss</sub>, not &#189;C&#183;V&#178; with a fixed C. It depends only "
       "on V<sub>OUT</sub> and f<sub>sw</sub>, so it is essentially line-independent.")
    eq_box(story, [r"P_{oss}=N_{ch}\,f_{sw}\,E_{oss}(V_{OUT})"], number="7.4.3", ch=CH)
    _worked(story, "7.4.3", "Output-Capacitance Loss — Worked Derivation", [
        ("E<sub>oss</sub>(V<sub>OUT</sub>)",
         lambda tr: f"E<sub>oss</sub>({_f(tr['Vo'],1)} V) = {_uj(tr['eoss_vo'])}"),
        ("P<sub>oss</sub> = N<sub>ch</sub>&#183;f<sub>sw</sub>&#183;E<sub>oss</sub>",
         lambda tr: f"{nch}&#215;{_f(tr['fsw']/1e3,0)}kHz&#215;{_uj(tr['eoss_vo'])} = <b>{_f(tr['P_oss_tot'])} W</b>"),
    ], traces)
    _basis(story, mosfet, ["E_oss_vs_VDS"], {
        "E_oss_vs_VDS": (
            f"Read at the actual bus, V<sub>OUT</sub> = {_f((traces[0][1] if traces else {}).get('Vo', 0), 1)} V, "
            f"giving {_uj((traces[0][1] if traces else {}).get('eoss_vo', 0))} &#8212; the energy "
            f"dissipated every switching cycle in the derivation above. Taking the datasheet's "
            f"400 V table value instead would misstate it."),
    })

    sub_h(story, "7.4.4", "Diode charge dumped into the FET", CH)
    _W(story,
       "<b>Model.</b> At MOSFET turn-on the boost diode is commutated off and its charge is removed "
       "<i>through the FET channel</i>, so this energy heats the MOSFET. For a Si diode it is the "
       f"reverse-recovery charge Q<sub>rr</sub> swept out under V<sub>OUT</sub> ({_frac*100:.0f} % of "
       "Q<sub>rr</sub>&#183;V<sub>OUT</sub> to the FET, the rest to the diode). For a SiC Schottky there "
       "is no minority-carrier recovery, but its junction-capacitance charge Q<sub>c</sub> is charged "
       "through the channel. The bus supplies V<sub>OUT</sub>&#183;Q<sub>c</sub> to do it; part of "
       "that stays STORED in the junction capacitance and is returned at the next turn-off, when "
       "the inductor charges the switch node. What the MOSFET dissipates is the difference, which "
       "for C<sub>j</sub>&#8733;v<sup>&#8722;m</sup> is exactly V<sub>OUT</sub>Q<sub>c</sub>/(2&#8722;m). "
       "<b>The silicon term is gated to CCM</b> — in DCM the diode current already reaches zero "
       "before the MOSFET turns on, so there is no hard recovery. The SiC junction charge is "
       "counted at every switching cycle, including the DCM portion near the zero crossings at high "
       "line; there the drain has already resonated below V<sub>OUT</sub>, so that share is "
       "slightly overstated. It reaches DCM only at the top of the input range and only for about "
       "a tenth of the half-cycle, so the effect is well under 0.2 W.")
    eq_box(story, [r"P_{rr\to FET}=N_{ch}\,f_{sw}\,\frac{V_{OUT}\,Q_c}{2-m}\ \mathrm{(SiC)}\quad "
                   r"\mathrm{or}\quad N_{ch}\,f_{sw}\,k\,\overline{Q_{rr}V_{OUT}}\ \mathrm{(Si)}"],
           number="7.4.4", ch=CH)
    _m = float(traces[0][1].get("cj_grading", 0.0)) if traces else 0.0
    _kq = float(traces[0][1].get("qc_factor", 0.5)) if traces else 0.5
    if traces and traces[0][1].get("is_sic"):
        if _m > 0:
            annotation(story, "Qc SPLIT",
                f"m = {_m:.3f} is this part's junction grading coefficient, fitted from the two "
                f"capacitance values its datasheet publishes, so the dissipated share of the "
                f"capacitive charge is 1/(2&#8722;m) = <b>{_kq:.3f}</b>. The familiar &#189; is the "
                f"m = 0 case &#8212; a LINEAR capacitor &#8212; and no real junction is one. Using "
                f"&#189; here would understate this term by "
                f"{100*(_kq/0.5-1):.0f}%.<br/><br/>"
                f"<b>Not the datasheet's E<sub>c</sub> curve.</b> Vendors also plot capacitive "
                f"ENERGY against reverse voltage, and it is tempting to read this loss straight off "
                f"it. That energy is what remains STORED in the capacitance; it is handed back at "
                f"turn-off, not dissipated. Taking it as the loss would understate this term by "
                f"about 40%, in the same direction as the &#189; it replaced.", CH)
        else:
            annotation(story, "Qc SPLIT",
                "The dissipated share of the capacitive charge is being taken as &#189;, which is "
                "the LINEAR-capacitor value. It is used because this datasheet does not publish two "
                "junction-capacitance points, so the grading coefficient m could not be fitted. "
                "Real junctions run m = 0.33 to 0.5, where the share is 0.60 to 0.67, so this term "
                "is understated by roughly a quarter. Two C<sub>j</sub> values &#8212; one near 1 V "
                "and one at the rated V<sub>R</sub> &#8212; remove the assumption entirely, with no "
                "curve digitising.", CH)
    def _qrr_sub(tr):
        if tr["is_sic"]:
            return (f"{tr.get('qc_factor', 0.5):.3f}&#215;{_f(tr['Vo'],0)}V&#215;{_nc(tr['qc'])}"
                    f"&#215;{_f(tr['fsw']/1e3,0)}kHz&#215;{nch}")
        return (f"{tr.get('rr_fet_frac', 0.85):.2f}&#215;{_nc(tr['qrr_eff'])}"
                f"&#215;{_f(tr['Vo'],0)}V&#215;{_f(tr['fsw']/1e3,0)}kHz&#215;{nch}")
    _worked(story, "7.4.4", "Diode-Charge-into-FET — Worked Derivation", [
        (f"P<sub>rr&#8594;FET</sub> = N<sub>ch</sub>f<sub>sw</sub>&#183;V<sub>OUT</sub>Q<sub>c</sub>/(2&#8722;m) (SiC) / {_frac:.2f}&#183;Q<sub>rr</sub>V<sub>OUT</sub> (Si)",
         lambda tr: f"{_qrr_sub(tr)} = <b>{_f(tr['P_rr_fet_tot'])} W</b>"),
    ], traces)
    # The charge is the DIODE's, so its evidence comes off the diode's datasheet even though the
    # energy is dissipated here and booked to the MOSFET.
    _basis(story, diode, ["Q_c", "Q_c_vs_VR", "E_c_vs_VR", "C_j_vs_VR"], {
        "Q_c": "The published charge, moved to the design's bus voltage as shown above.",
    })

    sub_h(story, "7.4.5", "Gate drive + leakage", CH)
    _W(story,
       "<b>Model.</b> Every switching cycle the gate driver moves the total gate charge Q<sub>g</sub> "
       "through the gate-drive voltage V<sub>g</sub>; that Q<sub>g</sub>&#183;V<sub>g</sub> energy is "
       "dissipated in the gate-loop resistance each period. Off-state leakage "
       "(V<sub>OUT</sub>&#183;I<sub>DSS</sub>) is added when a leakage curve is supplied; it is usually "
       "negligible at these temperatures.")
    eq_box(story, [r"P_{gate}=N_{ch}\,f_{sw}\,Q_g\,V_g"], number="7.4.5", ch=CH)
    _worked(story, "7.4.5", "Gate-Drive + Leakage — Worked Derivation", [
        ("P<sub>gate</sub>+leak = N<sub>ch</sub>&#183;f<sub>sw</sub>&#183;Q<sub>g</sub>&#183;V<sub>g</sub>",
         lambda tr: f"{nch}&#215;{_f(tr['fsw']/1e3,0)}kHz&#215;{_nc(tr['qg'])}&#215;{_f(tr['vg_drive'],0)}V = <b>{_f(tr['P_gate_tot'] + tr['P_leak_fet_tot'])} W</b>"),
    ], traces)

    tot_txt = "; ".join(
        f"{vac:.0f} V &#8594; {_f(tr['P_cond_fet_tot'] + tr['P_sw_fet_tot'] + tr['P_oss_tot'] + tr['P_rr_fet_tot'] + tr['P_gate_tot'] + tr['P_leak_fet_tot'])} W"
        for vac, tr in traces)
    _W(story, f"<b>MOSFET total (all {nch} channels):</b> {tot_txt}. The full 9-point breakdown is Table 7.4.")


def _diode_section(story, traces, diode=None):
    nch = int(traces[0][1]["Nch"]) if traces else 1
    is_sic = bool(traces[0][1].get("is_sic", True)) if traces else True
    _frac = float(traces[0][1].get("rr_fet_frac", 0.85)) if traces else 0.85
    _d = diode or {}
    _tech = _d.get("_technology") or {}
    _W(story,
       "<b>Model.</b> The boost diode conducts the inductor current during the MOSFET off-time, "
       "i<sub>D</sub> = i<sub>ch</sub>&#183;(1&#8722;d). Its conduction loss is the cycle-average of the "
       "current-dependent forward drop V<sub>f</sub>(i,T<sub>j</sub>) times i<sub>D</sub>.")
    annotation(story, "REVERSE Qrr",
        ("<b>Is reverse-recovery loss computed? Yes.</b> It is evaluated at every line angle in CCM only — "
         "in DCM the diode current already reaches zero before the MOSFET turns on, so there is no hard "
         "recovery. " +
         ("For the selected <b>SiC Schottky</b> diode there is no minority-carrier reverse recovery "
          "(Q<sub>rr</sub> = 0): it is a majority-carrier device. The only stored charge is the "
          "junction-capacitance Q<sub>c</sub>, which is swept through the MOSFET channel at turn-on, so it "
          "is booked to the MOSFET (Section 7.4.4). The diode's own reverse-recovery loss is therefore "
          "0 W — this is a key reason SiC is chosen for the boost diode."
          if is_sic else
          f"For the selected <b>Si</b> diode the recovery energy Q<sub>rr</sub>&#183;V<sub>OUT</sub> is "
          f"split between the two devices: {_frac*100:.0f} % is dissipated in the MOSFET at its hard "
          f"turn-on (Section 7.4.4) and {(1-_frac)*100:.0f} % in the diode itself; both shares scale "
          f"with f<sub>sw</sub>, the recovered charge Q<sub>rr</sub>(I<sub>F</sub>, di/dt, "
          f"T<sub>j</sub>) and V<sub>OUT</sub>.")), CH)
    _W(story,
       "The diode's own switching term is therefore "
       + ("its forward-recovery energy E<sub>fr</sub> only (Q<sub>c</sub> &#8594; FET); usually negligible."
          if is_sic else "its &#8776; 15 % share of the Q<sub>rr</sub> recovery energy."))
    eq_box(story, [r"i_D(\theta)=i_{ch}(\theta)\,(1-d(\theta)),\qquad P_{cond}=N_{ch}\,\overline{\,V_f(i_D,T_j)\,i_D\,}",
                   r"P_{sw,D}=N_{ch}\,f_{sw}\,E_{fr}\ \mathrm{(SiC)}\quad\mathrm{or}\quad "
                   r"N_{ch}\,f_{sw}\,(1-k)\,\overline{Q_{rr}V_{OUT}}\ \mathrm{(Si)}"],
           number="7.5", ch=CH)
    _worked(story, "7.5.1", "Boost-Diode Loss — Worked Derivation", [
        ("i<sub>D,avg</sub> = avg[i<sub>ch</sub>(1&#8722;d)]", lambda tr: f"{_f(tr['i_d_avg'],3)} A"),
        ("V<sub>f</sub>(i<sub>D</sub>,T<sub>j</sub>)",
         lambda tr: f"&#8776; {_f(tr['vf_d_pk'],3)} V (T<sub>j</sub>={_f(tr['Tj_dio'],0)}{_DEG}C)"),
        ("P<sub>cond</sub> = N<sub>ch</sub>&#183;avg[V<sub>f</sub>&#183;i<sub>D</sub>]",
         lambda tr: f"{_f(tr['P_cond_dio_tot'])} W"),
        ("P<sub>sw,D</sub>",
         lambda tr: (f"{_f(tr['P_sw_dio_tot'])} W (fwd-recovery; Q<sub>c</sub>&#8594;FET)"
                     if tr["is_sic"] else f"{_f(tr['P_sw_dio_tot'])} W (Q<sub>rr</sub> diode share)")),
        ("Diode total",
         lambda tr: f"<b>{_f(tr['P_cond_dio_tot'] + tr['P_sw_dio_tot'])} W</b>"),
    ], traces)
    _dtr = traces[0][1] if traces else {}
    _basis(story, diode, ["V_F_vs_IF", "V_F_vs_IF_hot", "I_rev_vs_Tj", "I_rev_vs_VR"], {
        "V_F_vs_IF": (
            f"The forward drop is integrated ALONG this curve rather than taken at one point: at "
            f"the {_f(_dtr.get('i_d_avg', 0), 2)} A average diode current and "
            f"T<sub>j</sub> = {_f(_dtr.get('Tj_dio', 0), 0)}{_DEG}C it reads "
            f"&#8776; {_f(_dtr.get('vf_d_pk', 0), 3)} V, the value in the derivation above."),
        "V_F_vs_IF_hot": (
            "The second temperature the per-point V<sub>f</sub> interpolates towards, so the drop "
            "falls with junction temperature the way the device does."),
    })

    # ── datasheet-first material (M8). Printed only when the block came from an uploaded
    # datasheet: a catalogue-sourced diode has none of this to show, and inventing a basis line
    # for it would be worse than staying silent.
    if _tech:
        annotation(story, "DIODE TECH",
            f"The recovery model above was chosen from the <b>datasheet</b>, not from the tab the "
            f"file was uploaded under: {_tech.get('basis','')}. This matters because "
            f"<code>is_sic</code> defaults to true in the loss engine, and the two branches are "
            f"different physics &#8212; a silicon part evaluated as SiC would have its largest "
            f"loss term computed by the wrong formula, silently and with no missing value to "
            f"give it away.", CH)
        if _tech.get("override"):
            annotation(story, "TECH CHECK",
                f"This datasheet was uploaded under the "
                f"<b>{'SiC Schottky' if _tech.get('declared') else 'silicon'}</b> sub-tab but has "
                f"been calculated as <b>{'SiC Schottky' if _tech.get('is_sic') else 'silicon'}</b> "
                f"on the evidence above. Confirm the part is what was intended before this report "
                f"is used for sign-off.", CH)

    _qcb = _d.get("_qc_basis") or {}
    if _qcb.get("scaled"):
        annotation(story, "Qc AT BUS",
            f"Q<sub>c</sub> is a charge stored at a stated reverse voltage, and Section 7.4.4 "
            f"spends it at the bus voltage &#8212; so the published figure has to be moved there "
            f"rather than used as printed. {_qcb.get('note','')}", CH)

    _qrb = _d.get("_qrr_basis") or {}
    if _qrb.get("note") and not is_sic:
        annotation(story, "Qrr BASIS", _qrb["note"], CH)

    if _tech and not is_sic and traces:
        _c = (_qrb.get("conditions") or {})
        _ds_didt = _c.get("diF_dt")
        _rows = [["Design di/dt at the current peak",
                  f"{_f(traces[0][1].get('didt_pk', 0)/1e6, 0)} A/{_MU}s",
                  "from the MOSFET's own turn-on transition (Section 7.4.2)"]]
        if _ds_didt:
            _rows.append(["Datasheet di/dt for Q<sub>rr</sub>", f"{_f(float(_ds_didt),0)} A/{_MU}s",
                          "the condition the recovery charge was measured at"])
        _rows.append(["Recovery charge used", f"{_nc(_qrb.get('qrr', 0))}",
                      "used at its published value, NOT rescaled"])
        _rows.append([f"Split to the MOSFET", f"{_frac*100:.0f} %",
                      "an assumed partition, not a datasheet quantity"])
        data_table(story, "7.5.2", "Reverse-Recovery Basis",
            "Recovery charge rises with both forward current and di/dt. Where this design switches "
            "faster than the datasheet's test point, the charge is understated; slower, overstated. "
            "It is shown rather than rescaled because scaling one published point by an assumed "
            "shape would look like a correction while being a guess &#8212; the same reason the "
            "MOSFET's C<sub>rss</sub> is left unmapped in Section 7.4.2.",
            ["Quantity", "Value", "Basis"], _rows,
            col_widths=[CW*0.34, CW*0.20, CW*0.46], ch=CH)

    _nd = int(traces[0][1].get("n_die_shared", 1)) if traces else 1
    if _nd > 1:
        annotation(story, "SHARED CASE",
            f"This package carries <b>{_nd} dies</b>, one per interleaved channel, so every loaded "
            f"die's loss passes through the single case-to-sink interface while each junction sees "
            f"only its own leg through R<sub>&#952;jc</sub>. The junction temperature is therefore "
            f"T<sub>sink</sub> + P<sub>leg</sub>R<sub>&#952;jc</sub> + "
            f"{_nd}&#183;P<sub>leg</sub>R<sub>&#952;cs</sub>, not "
            f"P<sub>leg</sub>(R<sub>&#952;jc</sub>+R<sub>&#952;cs</sub>). The per-leg "
            f"R<sub>&#952;jc</sub> is the one used; a dual datasheet also quotes a per-device figure "
            f"about {_nd}&#215; smaller, which describes the whole package and would halve the "
            f"predicted rise if it were taken for the junction.", CH)

    _vrs = _d.get("_irev_at_VR") or []
    if _vrs:
        annotation(story, "LEAK BOUND",
            f"Reverse current is published at V<sub>R</sub> = "
            f"{', '.join(f'{v:.0f}' for v in _vrs)} V, not at the bus, and is used as published. "
            f"Schottky leakage rises steeply with reverse voltage, so the blocking term below is a "
            f"<b>conservative upper bound</b> rather than its value at this bus. It is not scaled: "
            f"the barrier-lowering law needs two voltage points to fit and this datasheet gives "
            f"one, and an invented law would read as a correction while being a guess. The term is "
            f"small, so the cost of carrying the bound is small.", CH)

    _chk = [c for c in (_d.get("_checks") or []) if c.get("severity") == "check"]
    if _chk:
        annotation(story, "DIODE OPEN",
            "Open points on the diode's own parameters, carried here so they are not lost between "
            "the selection screen and this chapter: "
            + " &#183; ".join(f"<b>{c['key']}</b> &#8212; {c['message']}" for c in _chk), CH)


def _thermal_section(story, traces, thermal):
    tamb = float(thermal.get("t_ambient", 45)); rsa = float(thermal.get("rth_sa", 0.35))
    _W(story,
       "<b>Model.</b> Each device sits on a steady-state thermal-resistance ladder junction &#8594; case "
       "&#8594; heatsink &#8594; ambient. The shared sink rises above ambient by the <i>total</i> "
       "dissipation times R<sub>&#952;,sink-amb</sub>; each junction then rises above the sink by its "
       "<i>own</i> dissipation times (R<sub>&#952;jc</sub>+R<sub>&#952;cs</sub>). The solve is iterated "
       "because R<sub>ds(on)</sub>, V<sub>f</sub> and E<sub>sw</sub> themselves depend on T<sub>j</sub> "
       "— the numbers below are the converged values.")
    eq_box(story, [r"T_{sink}=T_{amb}+P_{\Sigma}\,R_{\theta,sa}",
                   r"T_j=T_{sink}+P_{dev}\,(R_{\theta,jc}+R_{\theta,cs})"], number="7.6", ch=CH)
    _worked(story, "7.6.1", "Thermal Network — Worked Derivation", [
        ("T<sub>sink</sub> = T<sub>amb</sub> + P<sub>&#931;</sub>&#183;R<sub>&#952;,sa</sub>",
         lambda tr: f"{_f(tamb,0)}{_DEG}C + {_f(tr['Psemi_main'] + tr['P_bridge'],1)}W&#215;{_f(rsa,2)} = {_f(tr['sink_main'],1)}{_DEG}C"),
        ("T<sub>j,FET</sub>", lambda tr: f"{_f(tr['Tj_fet'],1)}{_DEG}C"),
        ("T<sub>j,diode</sub>", lambda tr: f"{_f(tr['Tj_dio'],1)}{_DEG}C"),
        ("T<sub>j,bridge</sub>", lambda tr: f"{_f(tr['Tj_brT'],1)}{_DEG}C"),
    ], traces)
    # P_SIGMA HERE IS NOT THE SEMICONDUCTOR TOTAL OF SECTION 7.8, and the difference is gate drive.
    # A designer reconciling the two chapters found the ~0.1 W gap and reasonably read it as an
    # arithmetic error; it is a real physical distinction that the report simply never stated
    # (C250, designer-reported).
    annotation(story, "NOTE",
        "<b>Why P<sub>&#931;</sub> here is smaller than the semiconductor total in Table 7.8b.</b> "
        "The heatsink carries only what is dissipated IN THE PACKAGES bolted to it &#8212; MOSFET "
        "and diode conduction, switching, output-capacitance and recovery loss, plus the bridge. "
        "<b>Gate-drive power is excluded</b>, because the gate charge is dissipated in the driver "
        "IC's output stage and the external R<sub>g</sub> resistors, not in the MOSFET die: it "
        "never crosses the junction-to-case path and cannot raise T<sub>j</sub>. Table 7.8b DOES "
        "include it, because that table accounts for every watt drawn from the supply, wherever it "
        "ends up. Both are correct; they answer different questions, and on this design they "
        "differ by the gate-drive term alone.", CH)


def build_semiconductor_story(story, design, mosfet, diode, bridge, thermal, tj_limit=None, extra=None):
    """Append the full Chapter-7 content to `story`. `extra` may carry the other-chapter loss
    parameters (dcr_mohm, rcs_mohm, core_loss_by_vac, cap_loss_by_vac, …) for the Section 7.8
    system loss budget."""
    extra = extra or {}
    tj_limit = tj_limit or {"fet": 150, "diode": 150, "bridge": 130}
    res = calculate_semiconductor_losses(design, mosfet, diode, bridge, thermal, tj_limit)
    cfg, ref = build_semi_cfg(design, mosfet, diode, bridge, thermal)
    ops, s2, L_phi, iph, L_pts = build_design_ops(design)
    rows = res["per_point"]; summ = res["summary"]
    meta = ref["parts"]
    is_sync = cfg["bridge"].get("topology") == "sync_bottom"
    # Converged intermediate quantities at the two requested corners (low-line 90 V and the
    # mid-line 180 V worst case). The worked step-by-step tables are emitted at BOTH points;
    # the 9-point sweep tables follow. Pick the grid points closest to 90 and 180.
    vac_list = [float(v) for v in ops[:, 0]]
    _closest = lambda t: min(vac_list, key=lambda v: abs(v - t))
    worked_vacs = sorted({_closest(90.0), _closest(180.0)})
    traces = []
    for v in worked_vacs:
        try:
            traces.append((v, trace_point(design, mosfet, diode, bridge, thermal, vac=v)))
        except Exception:
            pass

    chapter_splash(story, CH, _TITLE,
        "How much do the power semiconductors dissipate, and do they stay within their "
        "junction-temperature limits across the whole line range?",
        ["7.1 Operating-point basis — the same 9-point grid used by every chapter",
         "7.2 Selected components — bridge, MOSFET, diode (datasheet + application)",
         "7.3 Bridge rectifier loss  ·  7.4 MOSFET loss (every mechanism)  ·  7.5 Boost-diode loss",
         "      each with a step-by-step worked substitution at the worst-case point + the full 9-point sweep",
         "7.6 Thermal network and junction temperatures",
         "7.7 Loss & temperature vs line voltage  ·  7.8 Summary and efficiency cross-check"])

    # #8 - state the chapter's standing up front. The efficiency cross-check in 7.8 is explicitly
    # an upper bound, and the thermal network is a design-stage estimate, not a qualification.
    annotation(story, "SCOPE",
        "<b>What this chapter is, and what it is not.</b> This is <b>first-pass design-stage loss "
        "and thermal modelling</b>, not a final thermal "
        "qualification. It sizes devices and heatsinks and shows where the loss goes. Three limits "
        "to read it with: (1) the efficiency figures in Section 7.8 are computed from the "
        "<b>accounted</b> losses only, so they are an <b>upper bound</b> on achievable efficiency "
        "and not a predicted efficiency; (2) junction temperatures come from a steady-state "
        "R<sub>th</sub> network &#8212; line-frequency junction ripple is not modelled unless a "
        "Foster Z<sub>th</sub> is supplied; and (3) several device parameters are interpolated or "
        "estimated from the datasheet scalars available (flagged per parameter in Section 7.2). "
        "Final numbers require bench measurement on the built hardware.", CH)

    # ── 7.1 Operating-point basis ────────────────────────────────────────────
    step_h(story, "7.1", "Operating-Point Basis", CH)
    annotation(story, "CONCEPT",
        "Every loss in this chapter is evaluated at the design's nine operating points using the "
        "efficiency, power factor, output power, total input RMS current and per-phase inductance "
        "carried in from the upstream chapters — not re-derived here. A consistency gate checks the "
        "engine's echoed operating point against those upstream values at every point, so the "
        "semiconductor numbers can never diverge from the rest of the design.", CH)
    L_varies = len({round(float(x) * 1e6, 1) for x in L_pts}) > 1
    if res["consistency"] and res["consistency"]["ok"]:
        annotation(story, "NOTE",
            "Consistency gate: PASS — Vac, P_out, P_in, &#951;, PF, I_in,rms, I_pk and L&#966; match the "
            "approved design at all nine points." + (
                " L&#966; is bias-adjusted per operating point (see the L<sub>&#966;</sub> column)."
                if L_varies else " (L&#966; = %s &#181;H everywhere.)" % _f(L_phi * 1e6, 0)), CH)
    annotation(story, "METHOD",
        "<b>How the losses are computed — time domain.</b> Every loss in Section 7.3&#8211;7.6 is obtained by "
        "integrating over the LINE cycle, not from a single peak or RMS figure. The half-line current "
        "envelope is sampled at several hundred angles &#952;; at each angle the per-switching-cycle "
        "waveforms — channel current, diode current, the turn-on/turn-off instants and the inductor "
        "ripple &#916;I<sub>L</sub> — are reconstructed, the instantaneous loss is formed, then averaged "
        "over the cycle and (for switching terms) scaled by f<sub>sw</sub>. This captures the sinusoidal "
        "variation of current and duty that a peak/RMS shortcut misses, and it is why the "
        "junction-temperature solve is iterated: R<sub>ds(on)</sub>, V<sub>f</sub> and E<sub>sw</sub> all "
        "depend on the converged T<sub>j</sub>.", CH)
    annotation(story, "NOTE",
        "<b>CCM vs DCM.</b> At each line angle the converter is in continuous (CCM) or discontinuous "
        "(DCM) conduction. DCM occurs where the channel current falls below half the inductor ripple — "
        "near the line zero-crossings, and over a larger fraction of the cycle at high line / light load "
        "(the current is small relative to &#916;I<sub>L</sub>). In DCM the inductor current is a triangle "
        "with a dead-time, which raises the FET/diode RMS-to-average ratio, changes the switching "
        "currents, and removes diode reverse recovery. The engine detects this per angle; the DCM "
        "fraction of each operating point is the <b>DCM%</b> column below.", CH)
    fsw = float(design["fsw"]); vout = float(design["vout"])
    body(story,
        "The total input RMS current follows from the supplied efficiency and power factor; the "
        "per-phase inductor RMS is the Step-5 value (low-frequency + high-frequency ripple components "
        "integrated over the half line cycle). The per-phase peak-to-peak inductor ripple uses the "
        "<b>per-operating-point</b> inductance L<sub>&#966;</sub>(V<sub>AC</sub>): a powder core's "
        "permeability rolls off with DC bias (current), so the inductance is lowest at the "
        "highest-current operating point and recovers toward the no-load value where the bias is "
        "smaller. These are the Chapter-3 bias-adjusted inductances. All currents below use the SAME "
        "equations as Chapters 2 and 5, to three decimals:", CH)
    eq_box(story, [r"I_{in,rms}=\dfrac{P_{out}}{\eta\,V_{AC}\,PF},\qquad "
                   r"I_{\varphi,rms}=\sqrt{\dfrac{1}{\pi}\int_0^{\pi}\left(i_{\varphi}^2+i_{hf}^2\right)d\theta}",
                   r"d(\theta)=1-\dfrac{\sqrt{2}\,V_{AC}\sin\theta}{V_{OUT}},\qquad "
                   r"\Delta I_{L,pp}=\dfrac{V_{in,pk}\,D_{pk}}{L_{\varphi}(V_{AC})\,f_{sw}}"],
           number="7.1", ch=CH)
    data_table(story, "7.1", "Operating Points (identical to Chapters 2, 3 & 5)",
        "Currents from the Step-2 / Step-5 equations (3 decimals). &#916;I<sub>L,pp</sub> uses the "
        "bias-adjusted per-point inductance L<sub>&#966;</sub>(V<sub>AC</sub>) from Chapter 3 — "
        "L<sub>&#966;</sub> is lowest where the peak current (DC bias) is highest and recovers as the "
        "current falls.",
        ["V_AC", "P_out", "&#951; %", "PF", "I_in,rms", "I_&#966;,rms", "&#916;I_L,pp", "L_&#966;", "DCM%"],
        [[f"{s2['Vin_rms'][i]:.0f} V", f"{r['Po']:.0f} W", _f(r['eta_in_%'], 1), _f(r['PF_in'], 4),
          f"{_f(s2['Iin_rms'][i], 3)} A", f"{_f(iph[i], 3)} A",
          f"{_f(s2['Vin_pk'][i] * s2['Dpk'][i] / (L_pts[i] * fsw), 3)} A", f"{_f(L_pts[i] * 1e6, 0)} &#181;H",
          f"{_f(r['DCM_%'], 1)}"]
         for i, r in enumerate(rows)],
        col_widths=[CW*0.10, CW*0.11, CW*0.08, CW*0.10, CW*0.14, CW*0.14, CW*0.13, CW*0.11, CW*0.09], ch=CH)

    # ── 7.2 Selected components ──────────────────────────────────────────────
    sub_h(story, "7.2", "Selected Components", CH)
    def _part(kind, label):
        m = meta.get(kind, {}); p = cfg[kind]
        return [label, m.get("manufacturer", "—") or "—", m.get("part_number", "—") or "—",
                p.get("tech") or p.get("topology") or ("SiC" if p.get("is_sic") else "Si")]
    data_table(story, "7.2a", "Confirmed Power Semiconductors",
        "Manufacturer / part number and the technology selected for each block.",
        ["Block", "Manufacturer", "Part number", "Type"],
        [_part("bridge", "Bridge rectifier"), _part("mosfet", "Boost MOSFET"), _part("diode", "Boost diode")],
        col_widths=[CW*0.24, CW*0.26, CW*0.30, CW*0.20], ch=CH)
    # detailed datasheet + application parameters (from the engine dataclasses, defaults included)
    from app.mode_b.semiconductor import pfc_loss_model as _eng
    import numpy as _np
    _sp, _mos, _dio, _br, _th = _eng.design_from_dict(cfg)
    _vo = float(design["vout"])
    # A DIGITISED CURVE CANNOT BE PRINTED POINT BY POINT. This listed every point, which was fine
    # while a vf_curve was the engine's 3-4 point default (about 50 characters) and fatal once a
    # confirmed curve reached the block: 244 points is ~3170 characters, ~33 wrapped lines, and
    # ReportLab measured the row at 1724 pt against a 728 pt frame and refused the whole document
    # with "Flowable too large". The report generated nothing at all.
    # Short curves still print in full — that is the useful reading. Long ones are summarised by
    # their extent, which is what a parameter table is for; the curve itself is shown as the
    # datasheet figure it was read off, in the evidence panel of its own section.
    def _vf(c, n_full: int = 5):
        xs, ys = list(c[0]), list(c[1])
        if not xs:
            return "&#8212;"
        if len(xs) <= n_full:
            return ", ".join(f"{y:.2f} V&#64;{x:.0f} A".replace("&#64;", "@")
                             for x, y in zip(xs, ys))
        return (f"{len(xs)} points: {min(ys):.2f}&#8211;{max(ys):.2f} V "
                f"over {min(xs):.3g}&#8211;{max(xs):.3g} A")
    _eoss = float(_np.interp(_vo, _mos.eoss_at_v[0], _mos.eoss_at_v[1]))
    # The hot factor must be read AT the temperature the label names. This interpolated at a
    # hardcoded 125 degC while printing the curve's last temperature — invisible while every curve
    # ended at 125, and wrong the moment a datasheet curve ends at 175: it printed "x1.42 at
    # 175 degC" where the real ratio there is 1.64.
    _tco = _mos._tjcoef(); _thot = float(_tco[0][-1])
    _khot = float(_np.interp(_thot, _tco[0], _tco[1]))
    prows = [
        ["<b>Boost MOSFET</b>", "", ""],
        ["Technology", _mos.tech.upper(), "channel material"],
        [f"R<sub>ds(on)</sub> @25{_DEG}C", f"{_mos.rdson_25*1e3:.1f} m{_OHM}", f"&#215;{_khot:.2f} at {_thot:.0f}{_DEG}C (tempco)"],
        ["Total gate charge Q<sub>g</sub>", f"{_mos.qg*1e9:.0f} nC", f"gate drive V<sub>g</sub> = {_mos.vg_drive:.0f} V"],
        ["Input capacitance C<sub>iss</sub>", f"{_mos.ciss*1e12:.0f} pF", f"Q<sub>gd</sub> = {_mos.qgd*1e9:.1f} nC, V<sub>th</sub> = {_mos.vth:.1f} V"],
        [f"Output-cap energy E<sub>oss</sub>(V<sub>OUT</sub>)", f"{_eoss*1e6:.2f} {_MU}J", f"at V<sub>OUT</sub> = {_vo:.1f} V"],
        ["Gate resistor R<sub>g</sub>", f"{(_mos.rg_on or _mos.rg):.1f} {_OHM}", "drive-loop"],
        [f"R<sub>&#952;jc</sub> / R<sub>&#952;cs</sub>", f"{_mos.rth_jc:.2f} / {_mos.rth_cs:.2f} {_DEG}C/W", "junction&#8594;case&#8594;sink"],
        ["<b>Boost diode</b>", "", ""],
        ["Type", "SiC Schottky" if _dio.is_sic else "Si", "recovery behaviour"],
        ["Forward drop V<sub>f</sub>(i) @25{}C".format(_DEG), _vf(_dio.vf_curve), "datasheet V-I curve"],
    ] + ([[f"Forward drop V<sub>f</sub>(i) @{_dio.vf_thot:.0f}{_DEG}C", _vf(_dio.vf_curve_hot),
           "hot curve — per-point Tj interpolation"]] if _dio.vf_curve_hot is not None else []) + [
        ([f"Capacitive charge Q<sub>c</sub>", f"{_dio.qc*1e9:.0f} nC", "SiC: no Q<sub>rr</sub>"]
         if _dio.is_sic else [f"Recovery charge Q<sub>rr</sub>", f"{_dio.qrr*1e9:.0f} nC", "Si reverse recovery"]),
        [f"R<sub>&#952;jc</sub> / R<sub>&#952;cs</sub>", f"{_dio.rth_jc:.2f} / {_dio.rth_cs:.2f} {_DEG}C/W", ""],
        ["<b>Bridge rectifier</b>", "", ""],
        ["Topology", _br.topology, "diode or sync-bottom"],
        ["Forward drop V<sub>f</sub>(i) @25{}C".format(_DEG), _vf(_br.vf_curve), "per device"],
    ] + ([[f"Forward drop V<sub>f</sub>(i) @{_br.vf_thot:.0f}{_DEG}C", _vf(_br.vf_curve_hot),
           "hot curve — per-point Tj interpolation"]] if _br.vf_curve_hot is not None else []) + [
        ["Devices in parallel", f"{_br.n_parallel_top if _br.topology=='sync_bottom' else _br.n_parallel}",
         "packages share one arm each (split arrangement)" ],
    ] + ([[ "Worst-die share derate", f"{_br.share_worst:.2f}",
            "arm V<sub>f</sub> evaluated at the hottest die's current"]]
         if _br.share_worst else []) + [
        [f"R<sub>&#952;jc</sub> / R<sub>&#952;cs</sub>", f"{_br.rth_jc:.2f} / {_br.rth_cs:.2f} {_DEG}C/W",
         "package-level (per-package thermal)"],
    ] + ([[ "Surge ratings I<sub>FSM</sub> / I&#178;t",
            f"{_f(bridge.get('ifsm_A'),0)} A / {_f(bridge.get('i2t_A2s'),0)} A&#178;s",
            "verified vs Ch-8 inrush in Section 7.3.1"]]
         if bridge.get("ifsm_A") and bridge.get("i2t_A2s") else []) + [
        ["<b>Thermal / application</b>", "", ""],
        [f"Ambient T<sub>a</sub>", f"{_th.t_ambient:.0f} {_DEG}C", "worst-case"],
        [f"Heatsink R<sub>&#952;sa</sub>", f"{_th.rth_sa:.2f} {_DEG}C/W", "sink&#8594;ambient (shared)"],
    ]
    data_table(story, "7.2b", "Selected-Component Datasheet & Application Parameters",
        "The actual values fed to the loss engine (datasheet parameters as confirmed, engine defaults "
        "shown where a field was left blank). These drive every calculation in Section 7.3&#8211;7.6.",
        ["Parameter", "Value", "Note"], prows,
        col_widths=[CW*0.36, CW*0.30, CW*0.34], ch=CH)

    # Where a MOSFET quantity came off a PLOT rather than a table, say so and say what it replaced.
    # Same rule as the diode's Q_c and C_j bases above: a digitised shape is neither a table value
    # nor a fit, and the reader cannot tell which from the number alone. Labels are kept to tokens
    # of 7 characters or fewer — the annotation cell breaks on spaces only, so a longer unbroken
    # word splits mid-word.
    for _key, _lbl in (("_eoss_basis", "Eoss CURVE"), ("_crss_basis", "Crss CURVE"),
                       ("_rdson_tj_basis", "RDS(on) vs Tj"),
                       ("_rdson_id_basis", "RDS(on) vs Id")):
        _b = (mosfet or {}).get(_key) or {}
        if _b.get("note"):
            annotation(story, _lbl, _b["note"], CH)

    # #10 - model-source provenance. `to_block` already records WHICH parameters it had to
    # estimate (`_estimated`); that was never surfaced, so a reader could not tell a datasheet
    # scalar from an engine estimate. Same pattern as the material provenance table (Section 3.2.6).
    _EST_LABEL = {
        "rth_jc":          "R<sub>&#952;jc</sub> — from rated P<sub>d</sub> or by package",
        "rth_cs":          "R<sub>&#952;cs</sub> — assumed interface",
        "eoss_at_v":       "E<sub>oss</sub>(V) — scaled from die size (1/R<sub>DS(on)</sub>, V<sup>1.5</sup>)",
        "rdson_tj":        "R<sub>DS(on)</sub> tempco — generic Si/SiC curve",
        "qgd":             "Q<sub>gd</sub> — fraction of Q<sub>g</sub>",
        "vpl":             "V<sub>plateau</sub> — V<sub>th</sub> + 2 V",
        "qrr":             "Q<sub>rr</sub> — from t<sub>rr</sub> and I<sub>o</sub>",
        "qc":              "Q<sub>c</sub> — SiC typical",
        "vf_curve(slope)": "V<sub>f</sub>(i) SHAPE — anchored on the datasheet point, knee shape estimated",
        # Produced by the PDF extractor, which reads text but not plots: these are shapes fitted
        # through the ONE scalar it could find, so they are labelled separately from the DB
        # estimates above — the reader should know the plotted curve was never consulted.
        "vf_curve(pdf)":   ("V<sub>f</sub>(i) SHAPE — a straight two-point line fitted to the single "
                            "V<sub>F</sub> value read from the uploaded PDF; the datasheet's plotted "
                            "V-I curve was NOT read"),
        "eoss_at_v(pdf)":  ("E<sub>oss</sub>(V) — a V<sup>1.5</sup> extrapolation from the single "
                            "E<sub>oss</sub> value read from the uploaded PDF; the plotted curve was "
                            "NOT read"),
    }
    _prov_rows = []
    for _lbl, _blk in (("Bridge", bridge), ("MOSFET", mosfet), ("Diode", diode)):
        _est = list((_blk or {}).get("_estimated") or [])
        _pn = (_blk or {}).get("part_number") or "&#8212;"
        _mf = (_blk or {}).get("manufacturer") or "&#8212;"
        _src = (_blk or {}).get("_source")
        _prov_rows.append([f"<b>{_lbl}</b>", f"{_mf} {_pn}".strip(),
                           (str(_src) if _src else
                            ("datasheet URL on file" if (_blk or {}).get("datasheet_url")
                             else "<i>no datasheet link</i>")),
                           ("all model parameters datasheet-backed" if not _est else
                            "; ".join(_EST_LABEL.get(e, e) for e in _est))])
    data_table(story, "7.2d", "Model-Parameter Provenance — Datasheet vs Estimated",
        "Which numbers behind Sections 7.3&#8211;7.6 come from the part's datasheet and which the "
        "engine had to estimate from the scalars available. Estimated parameters are ordinary "
        "design-stage practice, but they are where a bench measurement is most likely to differ "
        "&#8212; supplying the real curve or value removes the approximation entirely.",
        ["Device", "Selected part", "Datasheet", "Parameters the engine ESTIMATED"],
        _prov_rows, col_widths=[CW*0.11, CW*0.25, CW*0.16, CW*0.48], ch=CH)

    # ── 7.2e ── WHERE EVERY ENGINE INPUT CAME FROM, one row per parameter.
    # The table above answers "did the engine estimate anything", which was the right question
    # while parts came from the parametric catalogue. A part built from its own datasheet raises a
    # different one — a value can now be a table entry, a curve read off a plot, something derived
    # from other entries, or a design input — and the block records which for EVERY key. None of
    # it reached the page, so a reviewer could see the number and not where it came from, which is
    # the one thing they cannot reconstruct for themselves.
    # Driven entirely by `_provenance`, so it cannot drift from what actually ran.
    _PROV_WORD = {
        "extracted": "datasheet table",
        "digitised": "datasheet CURVE",
        "derived":   "derived",
        "manual":    "your design input",
        "corrected": "you corrected it",
        "default":   "ENGINE DEFAULT",
    }
    _BASIS_OF = {"E_oss_vs_VDS": "_eoss_basis", "C_rss_vs_VDS": "_crss_basis",
                 "R_DS_on_vs_Tj": "_rdson_tj_basis", "R_DS_on_vs_ID": "_rdson_id_basis"}
    _src_rows = []
    for _lbl, _blk in (("Bridge", bridge), ("MOSFET", mosfet), ("Diode", diode)):
        _prov = (_blk or {}).get(_PROV_KEY) or {}
        if not _prov:
            continue
        _figs = {f["key"]: f for f in ((_blk or {}).get("_figure_images") or [])}
        _esw = (_blk or {}).get("_esw_basis") or {}
        for _k in sorted(_prov):
            _p = _prov[_k]
            _ev = ""
            if _p == "digitised":
                _b = (_blk or {}).get(_BASIS_OF.get(_k, "")) or {}
                if _b.get("checked") and _b.get("error_pct") is not None:
                    _ev = f"agrees with the table to {_b['error_pct']:.2f} %"
                elif _k in ("E_on_vs_ID", "E_off_vs_ID") and _esw.get("ok"):
                    _e = _esw["error_pct"].get("E_on" if "on" in _k else "E_off")
                    _ev = f"agrees with the table to {_e:.2f} %"
                elif _b.get("from_curve"):
                    _ev = "read across the plotted range"
                _pg = (_figs.get(_k) or {}).get("page")
                if _pg:
                    _ev += f"; plot on page {_pg}" if _ev else f"plot on page {_pg}"
            # The canonical key VERBATIM. This used to insert a zero-width space (U+200B) before
            # each underscore to let the narrow column wrap - but ReportLab's Helvetica has no
            # U+200B glyph and draws a notdef BOX for it, which is the row of black squares the
            # designer reported. It was also unnecessary: the widest key here is `dies_per_package`
            # at 65 pt against a 135 pt column, so nothing ever needed to wrap.
            _src_rows.append([f"{_lbl}", _k,
                              _PROV_WORD.get(_p, _p), _ev or "&#8212;"])
    if _src_rows:
        data_table(story, "7.2e", "Where Each Engine Input Came From",
            "One row per number the loss model consumes. A value read off a PLOT is neither a "
            "table entry nor a fit, so it is named separately and carries the check that justifies "
            "it: the plot and the parameter table are independent renderings of one measurement, "
            "and their agreement is what says the curve was read correctly. Anything reading "
            "ENGINE DEFAULT is a number nobody chose &#8212; there should be none.",
            ["Device", "Parameter", "Source", "Evidence"],
            _src_rows, col_widths=[CW*0.12, CW*0.28, CW*0.20, CW*0.40], ch=CH)
    annotation(story, "NOTE",
        "Datasheet parameters (R<sub>DS(on)</sub>, V<sub>f</sub> curves, Q<sub>g</sub>, E<sub>oss</sub>, "
        "R<sub>&#952;jc</sub> …) and the application inputs (gate drive, R<sub>g</sub>, R<sub>&#952;cs</sub>, "
        "T<sub>ambient</sub>, R<sub>&#952;sa</sub>) confirmed on the selection screen are used as-is; the "
        "validation gate blocks the calculation until every required field is present.", CH)
    # typ/max provenance: parts picked from the local DB carry an _estimated list naming which
    # loss/thermal parameters were estimated (vs read verbatim from the datasheet columns).
    _est_lines = []
    for _lbl, _blk in (("Bridge", bridge), ("MOSFET", mosfet), ("Diode", diode)):
        _e = (_blk or {}).get("_estimated")
        if _e:
            _est_lines.append(f"<b>{_lbl}</b>: {', '.join(str(x) for x in _e)}")
    if _est_lines:
        annotation(story, "PITFALL",
            "The following parameters were ESTIMATED by the component database (the anchor scalars "
            "are the datasheet MAX values; curve shapes / thermal figures are generic): "
            + " &#183; ".join(_est_lines)
            + ". Replace them with the part's real datasheet curves (incl. the hot V<sub>f</sub> "
            "curve) on the manual form before sign-off.", CH)
    data_table(story, "7.2c", "Loss-Model Summary — what is computed and how",
        "Every loss mechanism in Section 7.3&#8211;7.6, the model used, and the current basis. All are "
        "evaluated by time-domain integration over the line cycle (Section 7.1).",
        ["Mechanism", "Model / method", "Current basis"],
        [["Bridge conduction", "V<sub>f</sub>(i)&#183;i integrated; datasheet V-I curve", "average current"],
         ["MOSFET conduction", "R<sub>ds(on)</sub>(T<sub>j</sub>)&#183;I&#178;, duty-weighted; hot R<sub>ds</sub>", "on-state RMS"],
         # FOLLOWS WHAT ACTUALLY RAN. This row was a hardcoded "analytic ... (Miller)" and kept
         # saying so after the measured E(I_D) curves took over, so the one table a reviewer reads
         # to orient themselves contradicted Section 7.4.2 two pages later.
         ["MOSFET switching",
          ("datasheet E<sub>on</sub>/E<sub>off</sub>(I<sub>D</sub>) curves, de-bundled and "
           "R<sub>g</sub>-corrected (Section 7.4.2)"
           if (mosfet or {}).get("sw_method") == "esw" and ((mosfet or {}).get("_esw_basis") or {}).get("ok")
           else "analytic E<sub>on</sub>/E<sub>off</sub> from C<sub>iss</sub>/R<sub>g</sub>/Q<sub>gd</sub> (Miller)"),
          "i at switch instants"],
         ["MOSFET output cap", "f<sub>sw</sub>&#183;E<sub>oss</sub>(V<sub>OUT</sub>); datasheet energy curve", "&#8212; (voltage)"],
         ["Diode charge &#8594; FET", "Si Q<sub>rr</sub>&#183;V<sub>OUT</sub> split / SiC &#189;V<sub>OUT</sub>Q<sub>c</sub>; CCM only", "switch-off current"],
         ["Boost-diode conduction", "V<sub>f</sub>(i)&#183;i<sub>D</sub> integrated; datasheet V-I", "average current"],
         ["Gate + leakage", "f<sub>sw</sub>&#183;Q<sub>g</sub>&#183;V<sub>g</sub> (+ leakage)", "&#8212;"],
         ["Junction temperatures", "iterated R<sub>&#952;</sub> ladder j&#8594;c&#8594;sink&#8594;amb", "per-device P"]],
        col_widths=[CW*0.26, CW*0.52, CW*0.22], ch=CH)

    # ── 7.3 Bridge rectifier ─────────────────────────────────────────────────
    sub_h(story, "7.3", "Bridge Rectifier Loss", CH)
    # configuration schematic — selected by the designer's topology + parallel-device choice
    _cfg_img, _cfg_cap = _config_schematic(_br.topology, _br.n_parallel_top if is_sync else _br.n_parallel)
    if _cfg_img is not None:
        story.append(_cfg_img)
        body(story, f"<i>Figure 7.3 — Selected bridge configuration. {_cfg_cap}</i>", CH)
    _worst_br = max(rows, key=lambda r: r.get("P_BRIDGE_total") or 0.0) if rows else None
    _bridge_section(story, traces, is_sync, bridge,
                    _sharing_sweep(design, mosfet, diode, bridge, thermal),
                    _derating_check(design, bridge, _worst_br, thermal))
    # #9 - the sync-bottom arrangement is not obvious from the schematic alone: the bottom
    # diodes sit in PARALLEL with the bypass-FET channel and can take back part of the current.
    # Spell out the path so a reviewer can follow where each term in Table 7.3 comes from.
    if is_sync:
        annotation(story, "CURRENT PATH",
            "<b>How current flows in the sync-bottom bridge.</b> Over each half of the line cycle "
            "the return current has TWO parallel routes to the negative rail, and the split is set "
            "by which one drops less voltage:<br/><br/>"
            "<b>1. Top arm (diodes).</b> The line-side diode of the conducting arm carries the full "
            "input current; loss is V<sub>f</sub>(i)&#183;i. With packages in parallel each carries "
            "i/n and therefore sits lower on its own V-I curve &#8212; that is where paralleling "
            "helps.<br/>"
            "<b>2. Bottom arm (bypass FET).</b> A MOSFET replaces the return diode. Its drop is "
            "ohmic, i&#183;R<sub>DS(on)</sub>(T<sub>j</sub>), so it beats a diode knee at low and "
            "moderate current &#8212; the reason for the arrangement.<br/>"
            "<b>3. The bottom DIODE pair, in parallel with that FET.</b> R<sub>DS(on)</sub> rises "
            "with temperature, so near the line crest on a hot FET the ohmic drop i&#183;R can "
            "reach the diode knee. Beyond that point the diodes take back part of the current and "
            "the two conduct together.<br/><br/>"
            "The engine does not assume which wins: at every line angle it solves the node voltage "
            "v from <b>v/R<sub>DS(on)</sub> + n&#183;i<sub>diode</sub>(v) = i(&#952;)</b>, "
            "inverting the per-device forward curve at the bridge junction temperature. That is "
            "why Table 7.3 carries a separate bottom-diode share: it is a computed result, not an "
            "assumption. A lower hot R<sub>DS(on)</sub> restores full FET conduction and that "
            "share falls to zero.", CH)
    _has_bd = any(r.get("P_BRIDGE_bottom_bd", 0) > 0.01 for r in rows)
    # "TOP" AND "BOTTOM" ONLY MEAN ANYTHING IN A SYNC-BOTTOM BRIDGE, where the top half is diodes
    # and the bottom half is bypass MOSFETs. In a plain diode bridge there is no bottom device, so
    # the column printed 0.00 W at every line and an external reviewer read that as "all the loss
    # is in one package" — i.e. as a single-path model. The split is a topology artefact, not a
    # result, so it is shown only where it is one. Package-to-package sharing is Table 7.3.2.
    if is_sync:
        _hdr = ["V_AC", "I_in,rms", "P_bridge (top)", "P_bridge (bottom)", "P_bridge total"]
        _rws = [[f"{r['Vac']:.0f} V", f"{_f(r['Iin_rms'],1)} A", f"{_f(r['P_BRIDGE_top'])} W",
                 f"{_f(r['P_BRIDGE_bottom'])} W", f"{_f(r['P_BRIDGE_total'])} W"] for r in rows]
        _cw = [CW*0.14, CW*0.18, CW*0.22, CW*0.24, CW*0.22]
        _cap = "Conducting-pair loss at each operating point (top diodes + bottom MOSFETs)."
    else:
        _hdr = ["V_AC", "I_in,rms", "P_bridge total"]
        _rws = [[f"{r['Vac']:.0f} V", f"{_f(r['Iin_rms'],1)} A", f"{_f(r['P_BRIDGE_total'])} W"]
                for r in rows]
        _cw = [CW*0.28, CW*0.34, CW*0.38]
        _cap = ("Conducting-pair loss at each operating point. Two diodes conduct in series at "
                "every line angle, and where packages are paralleled each carries its share of "
                "the rectified current with its forward voltage evaluated at that shared current "
                "&#8212; the sensitivity of the result to how evenly they share is Table 7.3.2.")
    data_table(story, "7.3", "Bridge Loss vs Line Voltage", _cap, _hdr, _rws,
               col_widths=_cw, ch=CH)
    # B18. Blocking loss is inside the totals above; say so, with the number, rather than leaving
    # the reader to assume it is either absent or already counted. Both states are stated
    # explicitly, because "we did not model it" and "we modelled it and it is 17 mW" are different
    # claims and only one of them can be checked against the page.
    _leak_w = max((r.get("P_BRIDGE_leak", 0.0) or 0.0) for r in rows) if rows else 0.0
    if _leak_w > 0:
        _leak_at = max(rows, key=lambda r: r.get("P_BRIDGE_leak", 0.0) or 0.0)
        annotation(story, "NOTE",
            "<b>Blocking (leakage) loss is included in the totals above.</b> Two of the four legs "
            "block at any instant, and they stand off the <i>line</i> voltage rather than the DC "
            "bus, so the term is 2&#183;mean(|v<sub>line</sub>|)&#183;I<sub>R</sub>(T<sub>j</sub>) "
            f"= <b>{_leak_w*1000:.1f} mW</b> at worst ({_leak_at['Vac']:.0f} V<sub>AC</sub>, "
            f"T<sub>j</sub> {_f(_leak_at.get('Tj_BRIDGE_top', 0), 0)} &#176;C). It is small enough "
            "to ignore in the budget and is reported only so that it is visibly accounted for "
            "rather than silently omitted &#8212; it rises steeply with junction temperature, so "
            "it is the kind of term that stops being negligible on a hotter design.", CH)
    else:
        annotation(story, "NOTE",
            "<b>Blocking (leakage) loss is not modelled for this part:</b> its datasheet supplies "
            "no I<sub>R</sub>(T<sub>j</sub>) curve, and a single published leakage point cannot "
            "become one &#8212; leakage changes by roughly a decade over the junction-temperature "
            "range, so interpolating a slope from one point would be inventing it. The omission is "
            "worth a few milliwatts at these temperatures (two legs block the line voltage, so "
            "roughly 2&#183;(2&#183;V<sub>pk</sub>/&#960;)&#183;I<sub>R</sub>), and it is stated "
            "here rather than left as a silent gap in the totals.", CH)
    if _has_bd:
        annotation(story, "NOTE",
            "The total includes a bottom-diode crest share (the bypass-FET ohmic drop exceeds the "
            "diode knee near the line crest, so the bridge's bottom diodes conduct part of the "
            "return current): worst case "
            f"{max(r.get('P_BRIDGE_bottom_bd', 0) for r in rows):.2f} W. A lower hot "
            "R<sub>DS(on)</sub> restores full FET conduction.", CH)

    # 3d option (a) — a reviewer looking at the block will see rd = 0 and read it as a missing
    # parameter. It is not: the resistive term lives in the V-I curve. Say so on the page, and be
    # explicit about the one real limitation (the scalar tempco) so it is not mistaken for an error.
    _rd_br = float(getattr(_br, "rd", 0.0) or 0.0)
    _tco_br = float(getattr(_br, "vf_tco", 0.0) or 0.0)
    _hot_br = getattr(_br, "vf_curve_hot", None) is not None
    annotation(story, "BASIS — HOW THE BRIDGE FORWARD DROP IS MODELLED",
        "The conduction loss is <b>V<sub>f</sub>(i)&#183;i</b> with V<sub>f</sub>(i) read from the "
        "part's forward V-I curve, plus a separate series term <b>r<sub>d</sub>&#183;i&#178;</b>. "
        + (f"For this part <b>r<sub>d</sub> = {_rd_br*1e3:.1f} m&#8486;</b>. " if _rd_br else
           "<b>For this part r<sub>d</sub> = 0, and that is correct — not a missing parameter.</b> "
           "The resistive behaviour is already carried by the slope of the V-I curve itself "
           "(typically 5&#8211;15 m&#8486; in the region above the knee), so the two must not both "
           "be populated from the same datasheet slope: doing so would count the I&#178;R term "
           "twice and overstate bridge loss. ")
        + "Because the curve carries the slope, <b>paralleling is modelled correctly</b>: each "
        "device carries i/n and therefore sits lower on its own curve, which is where the benefit "
        "of a second package comes from."
        + ("" if _hot_br else
           " <b>Known limitation.</b> With no hot datasheet curve available for this part, the "
           f"temperature dependence falls back to a single scalar (V<sub>f</sub> tempco = "
           f"{_tco_br:+.4f} V/&#176;C) applied at ALL currents. A real silicon rectifier's tempco "
           "is negative only below its crossover current (near the rated value) and turns positive "
           "above it. A constant negative tempco therefore makes a COOLER device look slightly "
           "worse, so the benefit of paralleling is understated here and can even invert on some "
           "parts. Supplying a hot V-I curve removes the approximation entirely &#8212; the engine "
           "interpolates between the cold and hot curves per current point."), CH)

    # ── surge-withstand verification (ties Chapter 7 to Chapter 8's inrush limit) ──
    _ifsm = bridge.get("ifsm_A"); _i2t = bridge.get("i2t_A2s")
    _inr = extra.get("inrush_pk_A"); _tau = extra.get("inrush_tau_ms")
    if _ifsm or _i2t:
        sub_h(story, "7.3.1", "Surge-current withstand vs the Chapter-8 inrush limit", CH)
        _srows = []
        if _ifsm:
            _srows.append(["I<sub>FSM</sub> (8.3 ms half-sine)", f"{_f(_ifsm,0)} A",
                           (f"NTC-limited inrush peak {_f(_inr,1)} A → "
                            f"{float(_ifsm)/max(float(_inr),1e-9):.1f}× margin"
                            if _inr else "compare vs the Chapter-8 NTC-limited inrush peak")])
        if _i2t:
            if _inr and _tau:
                # exponential precharge decay: ∫i²dt = I_pk²·τ/2
                _ev = float(_inr)**2 * (float(_tau)/1e3)/2.0
                _srows.append(["I&#178;t rating", f"{_f(_i2t,0)} A&#178;s",
                               f"inrush event I&#178;t = I<sub>pk</sub>&#178;&#183;&#964;/2 = "
                               f"{_f(_ev,1)} A&#178;s → {float(_i2t)/max(_ev,1e-9):.1f}× margin"])
            else:
                _srows.append(["I&#178;t rating", f"{_f(_i2t,0)} A&#178;s",
                               "compare vs I<sub>pk</sub>&#178;&#183;&#964;/2 of the Chapter-8 precharge"])
        data_table(story, "7.3.1", "Bridge Surge Ratings vs Inrush Event",
            ("Inrush figures carried in from the Chapter-8 NTC design"
             + (f" ({extra.get('inrush_part')})" if extra.get("inrush_part") else "")
             + "." if _inr else
             "Enter the Chapter-8 NTC result (generate the full report) to evaluate the margins."),
            ["Rating", "Value", "Check"], _srows,
            col_widths=[CW*0.30, CW*0.22, CW*0.48], ch=CH)

    # ── 7.4 MOSFET ───────────────────────────────────────────────────────────
    sub_h(story, "7.4", "Boost MOSFET Loss", CH)
    annotation(story, "THEORY",
        "The MOSFET loss is the sum of five mechanisms — ohmic conduction, hard-switching crossover, "
        "output-capacitance (E<sub>oss</sub>) dissipation, the diode charge dumped into the FET, and "
        "gate-drive + leakage. Each is modelled below in its own sub-section: the equation we use, why "
        "that model is appropriate, and the worked numbers at the 90 V and 180 V corners.", CH)
    _mosfet_section(story, traces, mosfet, diode)
    # THE COLUMN WAS CALLED "RR" FOR A PART WITH NO REVERSE RECOVERY. For a SiC Schottky the
    # energy dumped into the channel at turn-on is the diode's junction CHARGE Q_c, not recovery
    # charge, and the external review flagged the label as actively misleading. The header now
    # follows the technology that was actually resolved, because for a silicon diode it really is
    # Q_rr and renaming it unconditionally would trade one wrong label for another.
    # `is_sic` is resolved per section; the loss engine records what the diode block RESOLVED to
    # (which is not always the sub-tab it was uploaded under — settled at C210).
    is_sic = bool(traces[0][1].get("is_sic", True)) if traces else True
    _rr_hdr = "Diode Q<sub>c</sub>&#8594;FET" if is_sic else "Diode Q<sub>rr</sub>&#8594;FET"
    data_table(story, "7.4", "MOSFET Loss Breakdown vs Line Voltage",
        "Per-mechanism MOSFET loss (all channels), at every input voltage. The "
        + ("Q<sub>c</sub>" if is_sic else "Q<sub>rr</sub>") +
        " column is the boost diode's charge dissipated in the MOSFET channel at turn-on: it is a "
        "MOSFET loss, and it is deliberately NOT repeated in the diode total of Table 7.5.",
        ["V_AC", "Cond", "Switch", "Coss", _rr_hdr, "Gate+leak", "FET total"],
        [[f"{r['Vac']:.0f} V", _f(r['P_FET_cond']), _f(r['P_FET_sw']), _f(r['P_FET_coss']),
          _f(r['P_FET_rr']), _f(r['P_gate_driver'] + r['P_FET_leak']),
          f"{_f(r['P_FET_total'] + r['P_gate_driver'])} W"] for r in rows],
        col_widths=[CW*0.11, CW*0.12, CW*0.13, CW*0.12, CW*0.18, CW*0.16, CW*0.18], ch=CH)

    # ── 7.5 Boost diode ──────────────────────────────────────────────────────
    sub_h(story, "7.5", "Boost Diode Loss", CH)
    _diode_section(story, traces, diode)
    # LEAKAGE WAS COMPUTED AND NEVER SHOWN, so Conduction + Switching did not add up to the total
    # and a reader could only guess at the remainder. It is its own column now. The switching
    # column is named for the mechanism it actually contains — recovery — because for a SiC part
    # it is exactly zero and a bare "Switching" reads like an omission rather than a result.
    _sw_hdr = "Recovery Q<sub>rr</sub>" if not is_sic else "Recovery (Q<sub>rr</sub>)"
    data_table(story, "7.5", "Diode Loss vs Line Voltage",
        "Conduction, recovery and blocking loss of the boost diode(s), at every input voltage. "
        + ("This is a SiC Schottky: it has no minority-carrier recovery, so the recovery column is "
           "exactly zero, and its junction charge Q<sub>c</sub> is booked to the MOSFET in "
           "Table 7.4 rather than counted again here. "
           if is_sic else "") +
        "The three columns sum to the total, so nothing is hidden in the remainder.",
        ["V_AC", "Conduction", _sw_hdr, "Blocking (leak)", "Diode total"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['P_D_cond'])} W", f"{_f(r['P_D_sw'])} W",
          f"{_f(r.get('P_D_leak', 0.0), 3)} W", f"{_f(r['P_DIODE_total'])} W"]
         for r in rows],
        col_widths=[CW*0.13, CW*0.21, CW*0.23, CW*0.22, CW*0.21], ch=CH)

    # ── 7.6 Thermal ──────────────────────────────────────────────────────────
    sub_h(story, "7.6", "Thermal Network and Junction Temperatures", CH)
    _thermal_section(story, traces, thermal)
    data_table(story, "7.6", "Junction Temperatures vs Line Voltage",
        f"Ambient {_f(thermal.get('t_ambient', 45), 0)} &#176;C, sink R&#952; "
        f"{_f(thermal.get('rth_sa', 0.35), 2)} &#176;C/W. Limits: FET {tj_limit['fet']}, "
        f"diode {tj_limit['diode']}, bridge {tj_limit['bridge']} &#176;C.",
        ["V_AC", "T_sink", "Tj FET", "Tj Diode", "Tj Bridge", "Verdict"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['T_sink_main'],0)} &#176;C", f"{_f(r['Tj_FET'],0)} &#176;C",
          f"{_f(r['Tj_DIODE'],0)} &#176;C", f"{_f(r['Tj_BRIDGE_top'],0)} &#176;C",
          ("PASS" if (r['Tj_FET'] <= tj_limit['fet'] and r['Tj_DIODE'] <= tj_limit['diode']
                      and r['Tj_BRIDGE_top'] <= tj_limit['bridge']) else "CHECK")] for r in rows],
        col_widths=[CW*0.14, CW*0.16, CW*0.16, CW*0.18, CW*0.18, CW*0.18], ch=CH)
    annotation(story, "NOTE",
        "Bridge junction temperatures use PER-PACKAGE dissipation (total diode loss / number of "
        "packages) through the package-level R<sub>&#952;jc</sub> — for the split dual-bridge "
        "arrangement each package permanently carries one arm. Values above are cycle-averaged "
        "steady state; the line-frequency junction ripple (the 8.3 ms conduction bursts against "
        "the package Z<sub>&#952;</sub>(t)) adds only a few &#176;C for these packages and is "
        "evaluated only when a Foster Z<sub>&#952;</sub> network is supplied (zth_foster).", CH)

    # ── 7.7 Figures ──────────────────────────────────────────────────────────
    sub_h(story, "7.7", "Loss and Temperature vs Line Voltage", CH)
    try:
        from app.mode_b.semiconductor import pfc_loss_model as engine, pfc_visualization as viz
        # THE WORST-CASE POINT, not the first entry in the sweep. These two figures show a
        # per-mechanism breakdown and the switching waveforms, and they were drawn at
        # vac_list[0] = 90 Vac while the chapter is signed off at the worst case, 180 Vac and
        # 7 W higher. A reviewer studying the breakdown was studying the wrong operating point.
        sel = float(summ.get("worst_loss_Vac") or cfg["run"]["vac_list"][0])
        with tempfile.TemporaryDirectory() as td:
            files = viz.build_step4_visuals(cfg, selected_vac=sel, vac_list=cfg["run"]["vac_list"],
                                            output_prefix=os.path.join(td, "ch7"), backend=engine,
                                            tj_limits=tj_limit)
            for name, cap in [("losses_vs_vac", "Figure 7-1 — Semiconductor losses vs input voltage."),
                              ("temperatures_vs_vac", "Figure 7-2 — Junction temperatures vs input voltage."),
                              ("loss_breakdown",
                               f"Figure 7-3 — Per-mechanism loss breakdown at {sel:.0f} Vac, the "
                               f"WORST-CASE point of Table 7.8a, not an arbitrary corner."),
                              ("waveforms",
                               f"Figure 7-4 — Operating-point waveforms at {sel:.0f} Vac (worst case).")]:
                if name in files:
                    story.append(_img_path(files[name]))
                    body(story, cap, CH)
            # The same sweep as Figure 7-1, stacked: which MECHANISM dominates, and where
            # conduction hands over to the voltage-dependent terms. Lives here rather than beside
            # the budget table of Section 7.8b, which is gated on inductor and R_CS data from other
            # chapters and so never renders in a standalone Chapter 7.
            _stack = viz.plot_loss_stack_vs_vac(rows, os.path.join(td, "ch7_stack.png"))
            story.append(_img_path(_stack))
            body(story, "Figure 7-5 &#8212; Semiconductor loss budget by mechanism. Conduction "
                        "dominates at low line, where the current is highest; the "
                        "voltage-dependent terms take over as the line rises.", CH)
    except Exception:
        annotation(story, "NOTE", "Figures unavailable in this build.", CH)

    # ── 7.8 Summary + cross-check ────────────────────────────────────────────
    sub_h(story, "7.8", "Summary and Efficiency Cross-Check", CH)
    wr = max(rows, key=lambda r: r["P_SEMI_total"])   # worst-case operating point
    # PER OPERATING POINT, not four independent maxima. This table used to list
    # summary["P_FET_max"], ["P_DIODE_max"] and ["P_BRIDGE_max"] - each the largest value that
    # component reaches ANYWHERE on the line sweep, so on the reference design it showed a MOSFET
    # figure from 90 Vac beside a diode and a bridge from 180 Vac, under a caption naming a single
    # worst-case voltage. The three added to 68.25 W while the Total row (the max of the SUM, a
    # different quantity again) said 65.44 W - 2.81 W apart, with nothing to say why. The MOSFET
    # row also omitted gate drive, which lives outside P_FET_total.
    #
    # Every row is now ONE operating point, the columns add across, and the Total column is the
    # same P_SEMI_total that Section 7.8b's Semicond. column carries (C249, designer-reported).
    _wi = rows.index(wr)
    _sa_rows = [[f"{r['Vac']:.0f} V",
                 f"{_f(float(r['P_FET_total']) + float(r.get('P_gate_driver') or 0.0))}",
                 f"{_f(r['P_DIODE_total'])}",
                 f"{_f(r['P_BRIDGE_total'])}",
                 f"{_f(r['P_SEMI_total'])} W"] for r in rows]
    data_table(story, "7.8a", "Semiconductor Loss by Component vs Line Voltage (W)",
        "One row per operating point, so the columns ADD ACROSS to the total. The MOSFET column "
        "includes gate drive, as Table 7.4 does &#8212; gate charge is dissipated in the driver and "
        "the gate resistors, not the channel, but it is drawn from the supply and belongs in the "
        "budget. The <b>Total</b> column is the figure Section 7.8b carries in its Semicond. "
        "column, and the amber row is the worst-case operating point.",
        ["V_AC", "MOSFET (all ch, incl gate)", "Diode (all ch)", "Bridge", "Total semiconductor"],
        _sa_rows, col_widths=[CW*0.14, CW*0.27, CW*0.20, CW*0.17, CW*0.22],
        worst_rows=[_wi], ch=CH,
        interpretation=(
            f"Worst-case semiconductor dissipation is <b>{_f(wr['P_SEMI_total'])} W at "
            f"{wr['Vac']:.0f} V<sub>AC</sub></b> (amber). Each component peaks at its own line "
            f"voltage &#8212; the MOSFET at {max(rows, key=lambda r: r['P_FET_total'])['Vac']:.0f} V, "
            f"the diode at {max(rows, key=lambda r: r['P_DIODE_total'])['Vac']:.0f} V, the bridge at "
            f"{max(rows, key=lambda r: r['P_BRIDGE_total'])['Vac']:.0f} V &#8212; so the largest "
            f"TOTAL is not the sum of the largest parts, and only a single row is a real operating "
            f"condition."))
    annotation(story, "NOTE",
        f"<b>Junction-temperature margin at the worst point.</b> "
        f"T<sub>j</sub> FET {_f(summ['Tj_FET_max'],0)}&#176;C against a {tj_limit['fet']}&#176;C limit, "
        f"diode {_f(summ['Tj_DIODE_max'],0)}&#176;C against {tj_limit['diode']}&#176;C, "
        f"bridge {_f(summ['Tj_BRIDGE_max'],0)}&#176;C against {tj_limit['bridge']}&#176;C. These are "
        f"maxima over the whole sweep and each may occur at a different line voltage; the per-point "
        f"values and their verdicts are Table 7.6.", CH)
    body(story,
        "Because the design efficiency is an input, the total system loss is known exactly: "
        "P<sub>system</sub> = P<sub>out</sub>&#183;(1&#8722;&#951;)/&#951;. We now account for it component by "
        "component. The semiconductors are computed in this chapter; the inductor copper and core "
        "loss come from Chapter 4 and the capacitor ESR loss from Chapter 5; whatever remains is "
        "control / auxiliary. <b>Chapters 3 and 4 report the inductor PER PHASE</b> &#8212; this design "
        "has one inductor, with its own core, in each of the N<sub>ch</sub> channels, so both the "
        "copper and the core term are multiplied by N<sub>ch</sub> here. Counting only the copper "
        "that many times would drop a whole core's loss into the Balance column.", CH)
    eq_box(story, [r"P_{L}=N_{ch}\,(P_{Cu,\varphi}+P_{core,\varphi}),\qquad P_{R_{CS}}=N_{ch}\,I_{\varphi,rms}^2\,R_{CS}",
                   r"P_{system}=\dfrac{P_{out}(1-\eta)}{\eta}=P_{semi}+P_{L}+P_{cap}+P_{R_{CS}}+P_{other}"],
           number="7.8", ch=CH)
    dcr = (float(extra["dcr_mohm"]) / 1e3) if extra.get("dcr_mohm") else None
    rcs = (float(extra["rcs_mohm"]) / 1e3) if extra.get("rcs_mohm") else None
    nch = int(design.get("nch", 1))
    core_w = float(extra["core_loss_w"]) if extra.get("core_loss_w") is not None else 0.0   # Ch4 inductor core
    cap_w = float(extra["cap_loss_w"]) if extra.get("cap_loss_w") is not None else 0.0       # Ch5 worst case
    # Per-line capacitor bank loss straight from Chapter 5's ESR(T) engine, so this column IS
    # Table 5.3.1's P_bank column rather than a re-derivation. Falls back to the worst-case scalar.
    # Per-line inductor CORE loss (cycle-averaged basis) from Chapter 4's engine, so the Inductor
    # column tracks line voltage instead of holding one worst-case constant. Same pattern as the
    # capacitor column added in C171.
    _core_by_vac = extra.get("core_loss_by_vac") or {}
    def _core_at(vac):
        if not _core_by_vac:
            return core_w
        try:
            return float(_core_by_vac[round(float(vac))])
        except (KeyError, TypeError, ValueError):
            return float(_core_by_vac[min(_core_by_vac, key=lambda k: abs(float(k) - float(vac)))])
    # Per-line inductor COPPER, per phase, on the same cycle-averaged basis as the core and from the
    # same Chapter-4 row (Table 4.2 Pcu,avg). Preferred over re-deriving I_phi^2*DCR here, which
    # drops the HF skin/proximity term the engine already integrated. DCR remains the fallback for
    # state saved before the key existed, and the note below says which basis was actually used.
    _cu_by_vac = extra.get("cu_loss_by_vac") or {}
    def _cu_pp_at(vac, iphi):
        """Inductor copper for ONE phase at this line voltage."""
        if _cu_by_vac:
            try:
                return float(_cu_by_vac[round(float(vac))])
            except (KeyError, TypeError, ValueError):
                return float(_cu_by_vac[min(_cu_by_vac, key=lambda k: abs(float(k) - float(vac)))])
        return iphi * iphi * dcr if dcr else 0.0
    _cu_basis_engine = bool(_cu_by_vac)
    _cap_by_vac = extra.get("cap_loss_by_vac") or {}
    def _cap_at(vac):
        if not _cap_by_vac:
            return cap_w
        try:
            return float(_cap_by_vac[round(float(vac))])
        except (KeyError, TypeError, ValueError):
            # nearest declared line point — the two chapters sweep the same grid, so this is a guard
            _keys = [float(k) for k in _cap_by_vac]
            return float(_cap_by_vac[min(_cap_by_vac, key=lambda k: abs(float(k) - float(vac)))]) if _keys else cap_w
    if dcr or rcs:
        srcs = (f"R<sub>CS</sub> = {_f(extra['rcs_mohm'],2)} m{_OHM}, " if rcs else "")
        annotation(story, "NOTE",
            f"Loss-budget inputs carried in: inductor copper "
            + (f"taken PER LINE and PER PHASE from Chapter 4 Table 4.2 (P<sub>cu</sub>,avg column, "
               f"cycle-averaged basis &#8212; it carries the HF skin/proximity term that a plain "
               f"I<sup>2</sup>&#183;DCR does not)" if _cu_basis_engine else
               f"= I<sub>&#966;,rms</sub><sup>2</sup>&#183;DCR with DCR = "
               f"{_f(extra.get('dcr_mohm', 0),1)} m{_OHM}/phase (Chapter 4 per-line copper "
               f"unavailable in this run)")
            + f", inductor core loss "
            + (f"taken PER LINE and PER PHASE from Chapter 4 Table 4.2 (cycle-averaged basis; "
               f"{_f(core_w,2)} W per phase at the design corner)" if _core_by_vac
               else f"= {_f(core_w,2)} W per phase (Chapter 4)")
            + f", capacitor bank loss "
            + (f"{_f(cap_w,2)} W worst case at {_f(extra.get('cap_loss_worst_vac'),0)} Vac, taken PER LINE "
               f"from Chapter 5 Table 5.3.1 ({extra.get('cap_loss_n_cap','N')} caps &#215; per-cap ESR(T) loss)"
               if _cap_by_vac else f"{_f(cap_w,2)} W (Chapter 5)")
            + f", {srcs}across the per-phase RMS current I<sub>&#966;,rms</sub> from Chapter 5. The "
            f"<b>Inductor</b> column is N<sub>ch</sub> = {nch} &#215; (copper + core) per phase; the "
            f"<b>Capacitor</b> column is the bank ESR loss; the remaining <b>Balance</b> is "
            f"control / auxiliary (Ch 6). <b>This column does not match Chapter 3 Table 3.6.1, and "
            f"is not meant to</b> &#8212; that is the conservative first-pass estimate on the "
            f"crest basis, for one phase. Table 4.2a reconciles the three figures in one place.", CH)
        _bal_vals: list[float] = []
        brows = []
        for i, r in enumerate(rows):
            iphi = float(iph[i]); p_sys = float(r["P_SYSTEM_total"]); p_semi = float(r["P_SEMI_total"])
            # BOTH terms are PER PHASE and BOTH scale with N_ch. Counting copper for every channel
            # while counting core once was the C233 defect: an interleaved design has one core per
            # phase, so the second inductor's core loss simply vanished from the budget (2.1-3.4 W
            # here) and the Balance column absorbed it without any row looking wrong.
            p_lcu = nch * _cu_pp_at(r["Vac"], iphi)
            p_ind = p_lcu + nch * _core_at(r["Vac"])     # inductor TOTAL = N_ch x (copper + core)
            p_rcs = nch * iphi * iphi * rcs if rcs else 0.0
            p_cap = _cap_at(r["Vac"])                    # per-line, == Chapter 5 Table 5.3.1
            p_other = p_sys - p_semi - p_ind - p_rcs - p_cap
            brows.append([f"{r['Vac']:.0f} V", f"{_f(p_semi,1)}", f"{_f(p_ind,1)}", f"{_f(p_cap,2)}",
                          f"{_f(p_rcs,1)}", f"{_f(p_other,1)}", f"{_f(p_sys,1)} W"])
            _bal_vals.append(p_other)      # #7 - so the note can describe the ACTUAL data
        data_table(story, "7.8b", "System Loss Budget vs Line Voltage (W)",
            "Every system loss reconciled against P<sub>system</sub> from the efficiency. The <b>Inductor</b> "
            f"column is N<sub>ch</sub> = {nch} &#215; the PER-PHASE total of Chapter 4 Table 4.2 "
            "(P<sub>cu</sub>,avg + P<sub>core</sub>,avg at that line voltage) &#8212; the same engine, so "
            f"dividing this column by {nch} reproduces Table 4.2's P<sub>tot</sub> row for row. The "
            "averaged basis is used because it is the heat actually generated; the crest-point value is "
            "the saturation reference only. The <b>Capacitor</b> column is the per-line bank ESR loss "
            "taken directly from Chapter 5 Table 5.3.1 (P<sub>bank</sub> column) — again the same engine "
            "and the same ESR(T) at each point. The <b>Balance</b> = P<sub>system</sub> &#8722; (all the "
            "above) is the control / auxiliary remainder.",
            ["V_AC", "Semicond.", "Inductor (Cu+core*)", "Capacitor", "R_CS", "Balance (ctrl)", "System total"],
            brows, col_widths=[CW*0.12, CW*0.15, CW*0.19, CW*0.14, CW*0.12, CW*0.15, CW*0.13], ch=CH)
        _bal_min = min(_bal_vals) if _bal_vals else None
        annotation(story, "NOTE",
            "<b>Reading the Balance.</b> With inductor (copper + core) and capacitor loss now itemised, the "
            "Balance is the remaining control / auxiliary and unmodelled-loss allowance. If any row goes "
            "<i>negative</i>, the computed component losses already exceed the system loss implied by the "
            "assumed efficiency at that corner &#8212; the assumed efficiency is <b>optimistic</b> there and "
            "should be revisited. That is most likely at high line, where the assumed efficiency is highest "
            "and the implied system loss smallest. "
            + ("<b>In this design every row is positive</b>, so the assumed efficiency is consistent with "
               "the computed losses at all nine points."
               if _bal_min is not None and _bal_min >= 0 else
               (f"<b>In this design the Balance goes negative (minimum {_bal_min:.2f} W)</b>, so the "
                "assumed efficiency needs revisiting at that corner."
                if _bal_min is not None else ""))
            + " Surfacing exactly this kind of inconsistency is the purpose of the cross-check.", CH)
        wi = rows.index(wr); iw = float(iph[wi])
        plcu_w = nch * _cu_pp_at(wr["Vac"], iw); prcs_w = nch * iw * iw * rcs if rcs else 0.0
        pcore_w = nch * _core_at(wr["Vac"])          # one core per phase - see the table above
        p_ind_w = plcu_w + pcore_w
        _W(story,
           f"<b>At the worst-case point ({wr['Vac']:.0f} V<sub>AC</sub>):</b> of the "
           f"{_f(wr['P_SYSTEM_total'],1)} W system loss, the semiconductors take "
           f"{_f(wr['P_SEMI_total'],1)} W ({100*wr['P_SEMI_total']/max(wr['P_SYSTEM_total'],1e-9):.0f}%), "
           f"the inductor {_f(p_ind_w,1)} W ({nch} &#215; [copper {_f(plcu_w/max(nch,1),1)} + core "
           f"{_f(pcore_w/max(nch,1),1)}] per phase), the capacitor "
           f"{_f(cap_w,1)} W, the current-sense resistors {_f(prcs_w,1)} W, leaving "
           f"{_f(wr['P_SYSTEM_total']-wr['P_SEMI_total']-p_ind_w-cap_w-prcs_w,1)} W for control / auxiliary.")
        # ── realistic efficiency derived from the computed losses ──
        sub_h(story, "7.9", "Efficiency Re-Estimate from Computed Losses", CH)
        body(story,
            "The operating grid carries an <i>assumed</i> efficiency curve (a stored default for the "
            "2-stage interleaved stage). We now re-estimate it from the losses actually computed. The "
            "accounted losses here &#8212; semiconductor + inductor copper + R<sub>CS</sub> &#8212; are a "
            "<b>lower bound</b> on the total (core, capacitor ESR and control add more), so the "
            "efficiency they imply is an <b>upper bound</b> on what is achievable. Where the assumed "
            "efficiency exceeds this bound it is optimistic and the stored value should be lowered "
            "toward (or below) the re-estimate.", CH)
        eq_box(story, [r"\eta_{calc}(V_{AC})=\dfrac{P_{out}}{P_{out}+P_{semi}+P_{L,Cu}+P_{R_{CS}}}\;\geq\;\eta_{real}"],
               number="7.9", ch=CH)
        erows = []
        for i, r in enumerate(rows):
            iphi = float(iph[i]); po = float(r["Po"])
            # Same copper source as Table 7.8b, so the two sections cannot disagree. Core is
            # deliberately still excluded here - that is what makes eta_calc an UPPER bound.
            pacc = float(r["P_SEMI_total"]) + nch * _cu_pp_at(r["Vac"], iphi) + (nch * iphi * iphi * rcs if rcs else 0.0)
            eta_calc = 100.0 * po / (po + pacc)
            eta_ass = float(r["eta_in_%"])
            flag = "&#10003;" if eta_ass <= eta_calc + 1e-6 else "optimistic"
            erows.append([f"{r['Vac']:.0f} V", f"{_f(eta_ass,2)} %", f"&#8804; {_f(eta_calc,2)} %", flag])
        data_table(story, "7.9", "Assumed vs Computed-Loss Efficiency",
            "&#951;<sub>calc</sub> uses the accounted (computed) losses only, so it is an upper bound; the "
            "true efficiency is lower once core + capacitor + control are added. &#8220;optimistic&#8221; "
            "marks corners where the assumed &#951; already exceeds this bound.",
            ["V_AC", "&#951; assumed", "&#951; &#8804; (computed-loss)", "Verdict"],
            erows, col_widths=[CW*0.18, CW*0.27, CW*0.31, CW*0.24], ch=CH)
        annotation(story, "RECOMMENDATION",
            "Replace the stored efficiency for any corner flagged &#8220;optimistic&#8221; with a value at "
            "or below &#951;<sub>calc</sub>, then re-run &#8212; the line current, the losses and the "
            "Balance update consistently. This closes the loop between the assumed efficiency and the "
            "physics-based loss model.", CH)
    else:
        data_table(story, "7.8c", "Loss Budget Cross-Check vs Line Voltage",
            "System loss from the supplied efficiency, the semiconductor share, and the implied remainder "
            "(inductor + capacitor + control — see Chapters 3&#8211;6).",
            ["V_AC", "System loss", "Semiconductor", "Implied other"],
            [[f"{r['Vac']:.0f} V", f"{_f(r['P_SYSTEM_total'],1)} W", f"{_f(r['P_SEMI_total'],1)} W",
              f"{_f(r['P_OTHER_implied'],1)} W"] for r in rows],
            col_widths=[CW*0.18, CW*0.27, CW*0.27, CW*0.28], ch=CH)

    # ── 7.10 Sensitivity ─────────────────────────────────────────────────────
    # Deliberately AFTER the conclusion rather than inside it. The main line is read once, in
    # order; these answer the questions a reviewer asks when CHALLENGING a choice - what if the
    # gate drive were different, what happens at part load, and is the de-bundling defensible -
    # and each is a genuine re-run of the engine, not a formula, so it carries the thermal
    # iteration and the measured curves exactly as the headline numbers do.
    _sens = []
    try:
        from app.mode_b.semiconductor import pfc_loss_model as _eng2, pfc_visualization as _viz2
        _sv = float(summ.get("worst_loss_Vac") or cfg["run"]["vac_list"][0])
        with tempfile.TemporaryDirectory() as _td2:
            try:
                _sens.append((_viz2.plot_loss_vs_rg(cfg, os.path.join(_td2, "rg.png"),
                                                    backend=_eng2, selected_vac=_sv),
                    f"Figure 7-6 &#8212; MOSFET loss and junction temperature against gate "
                    f"resistance at {_sv:.0f} Vac. The gate resistor is the designer's own choice "
                    f"and the largest single lever on switching loss; the correction that makes "
                    f"this curve meaningful is read from the datasheet's own E vs R<sub>g</sub> "
                    f"plot (Section 7.4.2), not assumed."))
            except Exception:
                pass
            try:
                _sens.append((_viz2.plot_loss_vs_load(cfg, os.path.join(_td2, "load.png"),
                                                      backend=_eng2, selected_vac=_sv),
                    f"Figure 7-7 &#8212; Semiconductor loss and its share of the output against "
                    f"load at {_sv:.0f} Vac. Every other figure sweeps line voltage at full power; "
                    f"efficiency is normally specified across the load range, and light load is "
                    f"where the fixed terms stop being negligible against a conduction loss that "
                    f"falls with the square of current."))
            except Exception:
                pass
            try:
                _sens.append((_viz2.plot_debundling(mosfet, os.path.join(_td2, "deb.png")),
                    "Figure 7-8 &#8212; The published turn-on energy against the device overlap "
                    "the model actually uses. What is removed is a CONSTANT, not a fraction, "
                    "because it is set by the test voltage rather than the current, and it is "
                    "counted in Sections 7.4.3 and 7.4.4 instead. The remainder falling to about "
                    "zero at the lowest plotted current is the check that the subtraction is the "
                    "right size &#8212; overlap energy is proportional to current, so it must."))
            except Exception:
                pass
            if _sens:
                sub_h(story, "7.10", "Sensitivity — what moves these numbers", CH)
                body(story,
                     "Each sweep below re-runs the whole engine at every point, so it carries the "
                     "same thermal iteration, the same measured curves and the same de-bundling as "
                     "the headline result. None of it is a formula fitted to the answer.", CH)
                for _path, _cap in _sens:
                    story.append(_img_path(_path))
                    body(story, _cap, CH)
    except Exception as _e:
        # Visible, never silent. C232 put this section behind a bare `except: pass`, and C234 fixed
        # exactly that pattern for Table 4.2a while leaving it here - a whole section could vanish
        # and the build still looked clean (C241).
        annotation(story, "NOTE",
            "<b>Sensitivity figures unavailable in this build.</b> The headline losses and "
            "temperatures above are unaffected; only the what-if sweeps are missing. "
            f"({type(_e).__name__})", CH)


def _doc(target):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    return SimpleDocTemplate(target, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=18*mm, bottomMargin=18*mm, title="Chapter 7 — " + _TITLE)


def build_semiconductor_report(design, mosfet, diode, bridge, thermal, tj_limit=None, extra=None) -> bytes:
    """Standalone Chapter-7 PDF (merged after Chapters 1–6)."""
    from reportlab.platypus import PageBreak
    story = []
    build_semiconductor_story(story, design, mosfet, diode, bridge, thermal, tj_limit, extra)
    while story and isinstance(story[0], PageBreak):   # chapter_splash leads with a PageBreak
        story.pop(0)
    buf = io.BytesIO()
    _doc(buf).build(story)
    return buf.getvalue()
