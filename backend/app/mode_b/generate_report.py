"""
app/mode_b/generate_report.py
Generates the PFC Design Report (Steps 1–12) from the Mode A LangGraph state.
Returns: bytes (PDF content ready for HTTP response).
"""
from __future__ import annotations
import os, io, tempfile, warnings
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether,
)

from app.mode_b.calculations import (
    K_of_D, step2_input_params, step4_inductance,
    step5_phase_rms, step7_8_worst_case, gen_waveforms,
)

# ── Page geometry matching Steps 13-14/15 ─────────────────────────────────
PAGE_W, PAGE_H = A4
LM = RM = 20 * mm           # left / right margin
TM = 22 * mm                # top margin (leaves room for header band)
BM = 18 * mm                # bottom margin
_CW = PAGE_W - LM - RM     # 170 mm content width


# ── Parameter extraction from Mode A state ────────────────────────────────

def _extract_params(state: dict) -> dict:
    """Pull all confirmed parameters from the LangGraph state."""
    app   = state.get("intake", {}).get("application", {})
    topo_inputs = state.get("topology_specific_inputs", {})
    sel_topo = state.get("selected_topology") or "interleaved_boost_ccm"
    sel_mode = state.get("selected_mode")     or "ccm"
    n_phases = int(state.get("selected_channels") or 2)
    ctrl_mode = state.get("selected_controller_mode") or "digital"

    Vout        = float(app.get("output_bus_voltage_v", 393))
    Pout_high   = float(app.get("output_power_w_high_line", 3600))
    Pout_low    = float(app.get("output_power_w_low_line",  1700))
    fsw         = float(topo_inputs.get("recommended_frequency_hz") or 70000)
    f_line      = float(app.get("nominal_line_frequency_hz") or 60)
    r_input     = float(topo_inputs.get("default_crest_ripple_ratio") or 0.095)
    Vripple     = float(app.get("dc_bus_voltage_ripple_pk_pk_v", 20))
    vin_min     = float(app.get("vin_rms_min", 90))
    vin_max     = float(app.get("vin_rms_max", 264))
    ctrl_pref   = state.get("intake", {}).get("control", {}).get("control_preference", "Digital")
    sw_tech     = state.get("intake", {}).get("business", {}).get(
                      "preferred_switch_technology", ["Si", "SiC"])
    cooling     = state.get("intake", {}).get("thermal", {}).get("cooling_type", "fan_cooled")

    # Build default OPS table (9 operating points)
    OPS = np.array([
        [vin_min,  Pout_low,  0.945, 0.9987],
        [110,      Pout_low,  0.955, 0.9986],
        [120,      Pout_low,  0.965, 0.9985],
        [132,      Pout_low,  0.975, 0.9980],
        [180,      Pout_high, 0.965, 0.9889],
        [200,      Pout_high, 0.975, 0.9884],
        [220,      Pout_high, 0.985, 0.9790],
        [230,      Pout_high, 0.988, 0.9789],
        [vin_max,  Pout_high, 0.990, 0.9520],
    ], dtype=float)

    TOPO_LABEL = {
        "single_boost_ccm": "Single Boost — CCM",
        "interleaved_boost_ccm": "2-Phase Interleaved Boost — CCM",
        "totem_pole_ccm": "Totem-Pole PFC — CCM",
        "totem_pole_interleaved_ccm": "Totem-Pole Interleaved — CCM",
        "boost_crcm": "Single Boost — CrCM",
        "boost_dcm":  "Single Boost — DCM",
    }

    return dict(
        Vout=Vout, Pout_high=Pout_high, Pout_low=Pout_low,
        fsw=fsw, f_line=f_line, r_input=r_input,
        Vripple=Vripple, vin_min=vin_min, vin_max=vin_max,
        OPS=OPS, N_phases=n_phases,
        topology=TOPO_LABEL.get(sel_topo, sel_topo),
        topology_key=sel_topo, mode=sel_mode,
        ctrl_mode=ctrl_mode, ctrl_pref=ctrl_pref,
        sw_tech=", ".join(sw_tech) if isinstance(sw_tech, list) else str(sw_tech),
        cooling=cooling.replace("_", " ").title(),
    )


# ── Main entry point ───────────────────────────────────────────────────────

def generate_full_report(state: dict) -> bytes:
    """Generate complete Steps 1–12 PDF. Returns PDF bytes."""
    p   = _extract_params(state)
    IMG = tempfile.mkdtemp()

    plt.rcParams.update({"mathtext.fontset": "stix", "font.family": "STIXGeneral"})

    # ── Calculations ─────────────────────────────────────────────────────
    s2  = step2_input_params(p["Vout"], p["OPS"])
    s4  = step4_inductance(s2, p["r_input"], p["fsw"], p["Vout"])
    L_phi_calc = s4["L_calc"]
    # Selected L: round computed up to nearest 5 µH
    L_phi = round(L_phi_calc * 1e6 / 5) * 5 * 1e-6

    Vin_rms = s2["Vin_rms"]; Pout = s2["Pout"]; eta = s2["eta"]; PF = s2["PF"]
    Vin_pk  = s2["Vin_pk"];  Dpk  = s2["Dpk"];  Pin = s2["Pin"]
    Iin_rms = s2["Iin_rms"]; Iin_pk = s2["Iin_pk"]; KDpk = s2["KDpk"]

    n = len(Vin_rms)
    IL_rms = np.zeros(n); IL_LF = np.zeros(n); IL_HF = np.zeros(n)
    dIL_crest = np.zeros(n)
    for i in range(n):
        IL_rms[i], IL_LF[i], IL_HF[i], dIL_crest[i] = step5_phase_rms(
            Vin_pk[i], Iin_pk[i], L_phi, p["fsw"], p["Vout"])
    dIin_crest = KDpk * dIL_crest
    r_act      = dIin_crest / Iin_pk
    Iph_pk     = Iin_pk / 2 + dIL_crest / 2

    s78 = step7_8_worst_case(s2, L_phi, p["fsw"], p["Vout"], p["f_line"])
    th1  = s78["th1"]; th2 = s78["th2"]
    Vin_w = s78["Vin_w"]; D_w = s78["D_w"]
    t1_ms = s78["t1_ms"]; t2_ms = s78["t2_ms"]
    dIL_max = s78["dIL_max"]
    dIL_max_global = float(np.max(dIL_max))

    LLOW  = [i for i,v in enumerate(Vin_rms) if v <= 132]
    LHIGH = [i for i,v in enumerate(Vin_rms) if v >= 180]
    COLORS = ["#1F77B4","#D62728","#2CA02C","#9467BD",
               "#8C564B","#E377C2","#7F7F7F","#BCBD22","#17BECF"]
    BLUE = "#2F5496"

    PFONT = {"font.family":"DejaVu Serif","font.size":10.5,"axes.grid":True,
             "grid.alpha":0.30,"grid.linestyle":"--",
             "axes.spines.top":False,"axes.spines.right":False}
    plt.rcParams.update(PFONT)

    def save(fig, nm):
        path = os.path.join(IMG, nm)
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig); return path

    def render_eq(latex, fontsize=18, label="", width_in=6.5):
        plt.rcParams.update({"mathtext.fontset":"stix","font.family":"STIXGeneral"})
        fw, fh = 7.5, 0.95
        fig = plt.figure(figsize=(fw, fh)); fig.patch.set_facecolor("#F2F5FF")
        ax  = fig.add_axes([0,0,1,1]); ax.set_facecolor("#F2F5FF")
        ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
        for sp in ax.spines.values():
            sp.set_visible(True); sp.set_color("#9AABD8"); sp.set_linewidth(0.8)
        ax.text(0.47,0.50, latex, fontsize=fontsize, ha="center", va="center",
                color="#0D1B4B", transform=ax.transAxes)
        if label:
            ax.text(0.985,0.50, label, fontsize=10, ha="right", va="center",
                    color="#334477", transform=ax.transAxes, style="italic")
        slug = label.replace("(","").replace(")","_")
        path = os.path.join(IMG, f"eq_{slug}_{fontsize}.png")
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="#F2F5FF")
        plt.close(fig)
        h = width_in * (fh / fw)
        return [Image(path, width=width_in*inch, height=h*inch), Spacer(1,4)]

    # ── Plots ─────────────────────────────────────────────────────────────
    def single_plot(data, ylabel, title, fname):
        fig, ax = plt.subplots(figsize=(6.0,3.6))
        ax.plot(Vin_rms, data, color=BLUE, marker="o", ms=5, lw=2)
        ax.set_xlabel(r"$V_{\rm in,rms}$ (Vac)"); ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=12); ax.set_xlim(min(Vin_rms)-5, max(Vin_rms)+5)
        fig.tight_layout(); return save(fig, fname)

    p_dpk    = single_plot(Dpk,   r"$D_{\rm pk}$",
                           r"$D_{\rm pk}$ vs $V_{\rm in,rms}$",      "dpk.png")
    D_c = np.linspace(0.001,0.999,2000)
    fig,ax = plt.subplots(figsize=(6.0,4.0))
    ax.plot(D_c, K_of_D(D_c), color=BLUE, lw=2)
    ax.axvline(0.5, color="gray", ls="--", lw=0.9, label=r"$D=0.5$")
    ax.scatter(Dpk, KDpk, color="#C00000", zorder=5, s=30, label="Design points")
    ax.set_xlabel(r"$D$"); ax.set_ylabel(r"$K(D)$")
    ax.set_title(r"$K(D)$ vs Duty", fontsize=12)
    ax.set_xlim(0,1); ax.set_ylim(-0.02,1.05); ax.legend(fontsize=9)
    fig.tight_layout(); p_KD = save(fig, "KD.png")
    p_KDv  = single_plot(KDpk, r"$K(D_{\rm pk})$",
                         r"$K(D_{\rm pk})$ vs $V_{\rm in,rms}$",     "KDv.png")
    p_ilrms = single_plot(IL_rms, r"$I_{L,\phi,\rm rms}$ (A)",
                          r"$I_{L,\phi,\rm rms}$ vs $V_{\rm in,rms}$","il_rms.png")
    p_iinrms = single_plot(Iin_rms, r"$I_{\rm in,rms}$ (A)",
                           r"$I_{\rm in,rms}$ vs $V_{\rm in,rms}$",   "iin_rms.png")
    p_iinpk  = single_plot(Iin_pk,  r"$I_{\rm in,pk}$ (A)",
                           r"$I_{\rm in,pk}$ vs $V_{\rm in,rms}$",    "iin_pk.png")
    p_diin   = single_plot(dIin_crest, r"$\Delta I_{\rm in,pp}$ @ crest (A)",
                           r"$\Delta I_{\rm in,pp}$@crest vs $V_{\rm in,rms}$","diin.png")

    th90 = np.linspace(0,np.pi/2,800); th180 = np.linspace(0,np.pi,800)
    def dIL_curve(Vp, th):
        Vt=Vp*np.sin(th); Dt=np.clip(1-Vt/p["Vout"],0,1)
        return Vt*Dt/(L_phi*p["fsw"])

    fig,ax = plt.subplots(figsize=(6.4,4.0))
    for i in range(n):
        ax.plot(np.degrees(th90),dIL_curve(Vin_pk[i],th90),
                color=COLORS[i%9],lw=1.4,label=f"{int(Vin_rms[i])} Vac")
    ax.axhline(dIL_max_global,color="k",ls="--",lw=0.9)
    ax.set_xlabel(r"Line angle $\theta$ (deg)"); ax.set_ylabel(r"$\Delta I_{L,pp}$ (A pk-pk)")
    ax.set_title(r"$\Delta I_{L,pp}$ vs line angle (0–90°)")
    ax.legend(fontsize=7.5,ncol=3,framealpha=0.9); fig.tight_layout(); p6a=save(fig,"s6a.png")

    fig,ax = plt.subplots(figsize=(6.4,4.0))
    for i in range(n):
        ax.plot(np.degrees(th180),dIL_curve(Vin_pk[i],th180),
                color=COLORS[i%9],lw=1.4,label=f"{int(Vin_rms[i])} Vac")
    ax.axhline(dIL_max_global,color="k",ls="--",lw=0.9)
    ax.set_xlabel(r"Line angle $\theta$ (deg, 0–180)"); ax.set_ylabel(r"$\Delta I_{L,pp}$ (A pk-pk)")
    ax.set_title(r"$\Delta I_{L,pp}$ vs line angle (0–180°)")
    ax.legend(fontsize=7.5,ncol=3,framealpha=0.9); fig.tight_layout(); p6b=save(fig,"s6b.png")

    fig,ax = plt.subplots(figsize=(6.4,4.0))
    for k,i in enumerate(LHIGH):
        ax.plot(np.degrees(th90),dIL_curve(Vin_pk[i],th90),
                color=COLORS[k%9],lw=1.6,label=f"{int(Vin_rms[i])} Vac")
    ax.axhline(dIL_max_global,color="k",ls="--",lw=0.9)
    if LHIGH:
        th_wc=np.arcsin(p["Vout"]/2/Vin_pk[LHIGH[0]])
        ax.axvline(np.degrees(th_wc),color="gray",ls=":",lw=1.0)
    ax.set_xlabel(r"$\theta$ (deg)"); ax.set_ylabel(r"$\Delta I_{L,pp}$ (A pk-pk)")
    ax.set_title(r"High-line zoom: worst-case ($V_{\rm in}\approx V_{\rm out}/2$)")
    ax.legend(fontsize=9,framealpha=0.9); fig.tight_layout(); p6c=save(fig,"s6c.png")

    # Plot D — input ripple envelope after K(D) cancellation (low-line vs high-line)
    fig,axes=plt.subplots(2,1,figsize=(6.4,6.6))
    for ax2,idxs,ttl in[(axes[0],LLOW,"Low Line"),(axes[1],LHIGH,"High Line")]:
        for k,i in enumerate(idxs):
            Vt=Vin_pk[i]*np.sin(th90); Dt=np.clip(1-Vt/p["Vout"],0,1)
            ax2.plot(np.degrees(th90),K_of_D(Dt)*Vt*Dt/(L_phi*p["fsw"]),
                     color=COLORS[k%9],lw=1.5,label=f"{int(Vin_rms[i])} Vac")
        ax2.set_xlabel(r"Line angle $\theta$ (deg)")
        ax2.set_ylabel(r"$\Delta I_{\rm in,pp}(\theta)$ (A pk-pk)")
        ax2.set_title(f"Input Ripple Envelope after K(D) Cancellation \u2014 {ttl}")
        ax2.set_xlim(0,90); ax2.legend(fontsize=8,ncol=2)
    fig.tight_layout(pad=2.0); p6d=save(fig,"s6d.png")

    p8a = single_plot(np.degrees(th1),r"Worst-case angle $\theta_1$ (deg)",
                      r"Worst-case angle $\theta_1$ vs $V_{\rm in,rms}$","s8a.png")
    p8b = single_plot(dIL_max,r"$\Delta I_{L,pp,\rm max}$ (A)",
                      r"$\Delta I_{L,pp,\rm max}$ vs $V_{\rm in,rms}$","s8b.png")

    T_cyc = 1/p["f_line"]; t_cyc = np.linspace(0,T_cyc,2000)*1000
    p10=[]; groups=[[LLOW[i:i+3] for i in range(0,len(LLOW),3)]+
                    [LHIGH[i:i+3] for i in range(0,len(LHIGH),3)]][0]
    groups = [LLOW[:4], LHIGH[:3], LHIGH[3:]]
    for gi,grp in enumerate([g for g in groups if g]):
        nc=min(len(grp),3); nr=(len(grp)+nc-1)//nc
        fig,axes=plt.subplots(nr,nc,figsize=(nc*3.1,nr*2.8))
        if nr*nc==1: axes=np.array([[axes]])
        elif nr==1:  axes=axes.reshape(1,-1)
        elif nc==1:  axes=axes.reshape(-1,1)
        k2=0
        for row in axes:
            for ax2 in row:
                if k2<len(grp):
                    i=grp[k2]
                    Vt=Vin_pk[i]*np.abs(np.sin(2*np.pi*p["f_line"]*t_cyc/1000))
                    Dt=np.clip(1-Vt/p["Vout"],0,1)
                    ax2.plot(t_cyc,Dt,color=BLUE,lw=1.4)
                    ax2.axhline(Dpk[i],color="#C00000",ls="--",lw=0.9)
                    ax2.set_title(f"$V_{{\\rm ac}}={int(Vin_rms[i])}$ Vrms",fontsize=10)
                    ax2.set_xlabel("Time (ms)",fontsize=9); ax2.set_ylabel("D(t)",fontsize=9)
                    ax2.set_xlim(0,T_cyc*1000); ax2.set_ylim(-0.02,1.05); ax2.tick_params(labelsize=8)
                else: ax2.set_visible(False)
                k2+=1
        fig.suptitle("Duty cycle over 1 line cycle",fontsize=10,fontweight="bold")
        fig.tight_layout(); p10.append(save(fig,f"s10_{gi}.png"))

    th_h = np.linspace(1e-6,np.pi,1200)
    T_crest=1/(4*p["f_line"]); zh=90e-6

    def ripple_at(ph,D,dI):
        Ds=np.where(D>1e-7,D,1e-7); Rs=np.where(1-D>1e-7,1-D,1e-7)
        return np.where(ph<=D,dI*(ph/Ds-0.5),dI*(0.5-(ph-D)/Rs))

    fig,axes=plt.subplots(2,1,figsize=(6.4,6.6))
    for ax2,idxs,ttl in[(axes[0],LLOW,"Low Line"),(axes[1],LHIGH,"High Line")]:
        for k,i in enumerate(idxs):
            Vt=Vin_pk[i]*np.sin(th_h); Dt=np.clip(1-Vt/p["Vout"],0,1)
            ax2.plot(th_h/(2*np.pi*p["f_line"])*1000,Vt*Dt/(L_phi*p["fsw"]),
                     color=COLORS[k%9],lw=1.5,label=f"{int(Vin_rms[i])} Vac")
        ax2.axhline(dIL_max_global,color="k",ls="--",lw=0.8)
        ax2.set_xlabel("Time (ms)"); ax2.set_ylabel(r"$\Delta I_{L,pp}$ (A pk-pk)")
        ax2.set_title(f"Per-phase Ripple Envelope — {ttl}"); ax2.set_xlim(0,8.333)
        ax2.legend(fontsize=8,ncol=2)
    fig.tight_layout(pad=2.0); p11_1=save(fig,"s11_1.png")

    for tag,idxs,nm in[("Low Line",LLOW,"s11_2.png"),("High Line",LHIGH,"s11_3.png")]:
        fig,ax2=plt.subplots(figsize=(6.4,3.6))
        for k,i in enumerate(idxs):
            t_ms,_,_,rA,_,_,_,_=gen_waveforms(Vin_pk[i],Iin_pk[i],L_phi,p["fsw"],p["f_line"],p["Vout"])
            ax2.plot(t_ms,rA,color=COLORS[k%9],lw=0.4,alpha=0.85,label=f"{int(Vin_rms[i])} Vac")
        ax2.set_xlabel("Time (ms)"); ax2.set_ylabel(r"$\tilde{i}_{L\phi,A}(t)$ (A)")
        ax2.set_title(f"Per-phase Signed Ripple (Phase A) — {tag}")
        ax2.legend(fontsize=8,ncol=2); ax2.set_xlim(0,8.333); fig.tight_layout()
        if tag=="Low Line": p11_2=save(fig,nm)
        else:               p11_3=save(fig,nm)

    fig,axes=plt.subplots(2,1,figsize=(6.4,6.6))
    for ax2,idxs,ttl in[(axes[0],LLOW,"Low Line"),(axes[1],LHIGH,"High Line")]:
        for k,i in enumerate(idxs):
            Vt=Vin_pk[i]*np.sin(th_h); Dt=np.clip(1-Vt/p["Vout"],0,1)
            dIL_e=Vt*Dt/(L_phi*p["fsw"]); iavg_e=(Iin_pk[i]/2)*np.sin(th_h)
            t_ms_h=th_h/(2*np.pi*p["f_line"])*1000; c=COLORS[k%9]
            ax2.fill_between(t_ms_h,np.maximum(iavg_e-dIL_e/2,0),iavg_e+dIL_e/2,alpha=0.18,color=c)
            ax2.plot(t_ms_h,iavg_e+dIL_e/2,color=c,lw=1.2,label=f"{int(Vin_rms[i])} Vac")
            ax2.plot(t_ms_h,np.maximum(iavg_e-dIL_e/2,0),color=c,lw=1.2)
        ax2.set_xlabel("Time (ms)"); ax2.set_ylabel(r"$i_{L\phi,A}(t)$ (A)")
        ax2.set_title(f"Per-phase Current — {ttl}")
        ax2.legend(fontsize=8,ncol=2); ax2.set_xlim(0,8.333)
    fig.tight_layout(pad=2.0); p11_4=save(fig,"s11_4.png")

    for tag,idxs,nm in[("Low Line",LLOW,"s11_5L.png"),("High Line",LHIGH,"s11_5H.png")]:
        fig,ax2=plt.subplots(figsize=(6.4,3.6))
        for k,i in enumerate(idxs):
            t_z=np.linspace(T_crest-zh,T_crest+zh,300)
            th_z=2*np.pi*p["f_line"]*t_z
            Vt=Vin_pk[i]*np.sin(th_z); Dt=np.clip(1-Vt/p["Vout"],0,1)
            iavg_z=(Iin_pk[i]/2)*np.sin(th_z); dIL_z=Vt*Dt/(L_phi*p["fsw"])
            phA=(t_z*p["fsw"])%1.0
            ax2.plot((t_z-T_crest)*1e6,iavg_z+ripple_at(phA,Dt,dIL_z),
                     color=COLORS[k%9],lw=1.0,label=f"{int(Vin_rms[i])} Vac")
        ax2.set_xlabel(r"Time around crest ($\mu$s)"); ax2.set_ylabel(r"$i_{L\phi,A}(t)$ (A)")
        ax2.set_title(f"Switching ripple around crest — {tag}")
        ax2.legend(fontsize=8,ncol=2); fig.tight_layout()
        if tag=="Low Line": p11_5L=save(fig,nm)
        else:               p11_5H=save(fig,nm)

    if Vin_pk[0] > 0:
        fig,ax2=plt.subplots(figsize=(6.4,3.6))
        t_z=np.linspace(T_crest-zh,T_crest+zh,300); i=0
        th_z=2*np.pi*p["f_line"]*t_z
        Vt=Vin_pk[i]*np.sin(th_z); Dt=np.clip(1-Vt/p["Vout"],0,1)
        iavg_z=(Iin_pk[i]/2)*np.sin(th_z); dIL_z=Vt*Dt/(L_phi*p["fsw"])
        phA=(t_z*p["fsw"])%1.0; phB=(t_z*p["fsw"]+0.5)%1.0
        ax2.plot((t_z-T_crest)*1e6,iavg_z+ripple_at(phA,Dt,dIL_z),color=BLUE,lw=1.2,label="Phase A")
        ax2.plot((t_z-T_crest)*1e6,iavg_z+ripple_at(phB,Dt,dIL_z),color="#C00000",lw=1.2,
                 ls="--",label=r"Phase B ($T_s/2$ shift)")
        ax2.set_xlabel(r"Time around crest ($\mu$s)"); ax2.set_ylabel(r"$i_{L\phi}(t)$ (A)")
        ax2.set_title(f"Phase A vs Phase B at {int(Vin_rms[0])} Vac")
        ax2.legend(fontsize=9); fig.tight_layout(); p11_6=save(fig,"s11_6.png")
    else:
        p11_6=p11_5L

    fig,axes=plt.subplots(2,1,figsize=(6.4,6.6))
    for ax2,idxs,ttl in[(axes[0],LLOW,"Low Line"),(axes[1],LHIGH,"High Line")]:
        for k,i in enumerate(idxs):
            Vt=Vin_pk[i]*np.sin(th_h); Dt=np.clip(1-Vt/p["Vout"],0,1)
            ax2.plot(th_h/(2*np.pi*p["f_line"])*1000,
                     K_of_D(Dt)*Vt*Dt/(L_phi*p["fsw"]),
                     color=COLORS[k%9],lw=1.5,label=f"{int(Vin_rms[i])} Vac")
        ax2.set_xlabel("Time (ms)"); ax2.set_ylabel(r"$\Delta I_{\rm in,pp}(\theta)$ (A pk-pk)")
        ax2.set_title(f"Input Ripple Envelope — {ttl}"); ax2.set_xlim(0,8.333)
        ax2.legend(fontsize=8,ncol=2)
    fig.tight_layout(pad=2.0); p12_1=save(fig,"s12_1.png")

    for tag,idxs,nm in[("Low Line",LLOW,"s12_2.png"),("High Line",LHIGH,"s12_3.png")]:
        fig,ax2=plt.subplots(figsize=(6.4,3.6))
        for k,i in enumerate(idxs):
            t_ms,_,_,_,_,diin,_,_=gen_waveforms(Vin_pk[i],Iin_pk[i],L_phi,p["fsw"],p["f_line"],p["Vout"])
            ax2.plot(t_ms,diin,color=COLORS[k%9],lw=0.4,alpha=0.85,label=f"{int(Vin_rms[i])} Vac")
        ax2.set_xlabel("Time (ms)"); ax2.set_ylabel(r"$\delta i_{\rm in}(t)$ (A)")
        ax2.set_title(f"Signed Input Ripple — {tag}")
        ax2.legend(fontsize=8,ncol=2); ax2.set_xlim(0,8.333); fig.tight_layout()
        if tag=="Low Line": p12_2=save(fig,nm)
        else:               p12_3=save(fig,nm)

    fig,axes=plt.subplots(2,1,figsize=(6.4,6.6))
    for ax2,idxs,ttl in[(axes[0],LLOW,"Low Line"),(axes[1],LHIGH,"High Line")]:
        for k,i in enumerate(idxs):
            Vt=Vin_pk[i]*np.sin(th_h); Dt=np.clip(1-Vt/p["Vout"],0,1)
            dIin_e=K_of_D(Dt)*Vt*Dt/(L_phi*p["fsw"])
            iavg_e=Iin_pk[i]*np.sin(th_h); t_ms_h=th_h/(2*np.pi*p["f_line"])*1000; c=COLORS[k%9]
            ax2.fill_between(t_ms_h,iavg_e-dIin_e/2,iavg_e+dIin_e/2,alpha=0.18,color=c)
            ax2.plot(t_ms_h,iavg_e+dIin_e/2,color=c,lw=1.2,label=f"{int(Vin_rms[i])} Vac")
            ax2.plot(t_ms_h,np.maximum(iavg_e-dIin_e/2,0),color=c,lw=1.2)
        ax2.set_xlabel("Time (ms)"); ax2.set_ylabel(r"$i_{\rm in,total}(t)$ (A)")
        ax2.set_title(f"Total Input Current — {ttl}")
        ax2.legend(fontsize=8,ncol=2); ax2.set_xlim(0,8.333)
    fig.tight_layout(pad=2.0); p12_4=save(fig,"s12_4.png")

    for tag,idxs,nm in[("Low Line",LLOW,"s12_5L.png"),("High Line",LHIGH,"s12_5H.png")]:
        fig,ax2=plt.subplots(figsize=(6.4,3.6))
        for k,i in enumerate(idxs):
            t_z=np.linspace(T_crest-zh,T_crest+zh,300)
            th_z=2*np.pi*p["f_line"]*t_z
            Vt=Vin_pk[i]*np.sin(th_z); Dt=np.clip(1-Vt/p["Vout"],0,1)
            iavg_z=Iin_pk[i]*np.sin(th_z); dIL_z=Vt*Dt/(L_phi*p["fsw"])
            phA=(t_z*p["fsw"])%1.0; phB=(t_z*p["fsw"]+0.5)%1.0
            rA=ripple_at(phA,Dt,dIL_z); rB=ripple_at(phB,Dt,dIL_z)
            ax2.plot((t_z-T_crest)*1e6,iavg_z+rA+rB,color=COLORS[k%9],lw=1.0,
                     label=f"{int(Vin_rms[i])} Vac")
        ax2.set_xlabel(r"Time around crest ($\mu$s)"); ax2.set_ylabel(r"$i_{\rm in,total}(t)$ (A)")
        ax2.set_title(f"Total current — switching ripple around crest — {tag}")
        ax2.legend(fontsize=8,ncol=2); fig.tight_layout()
        if tag=="Low Line": p12_5L=save(fig,nm)
        else:               p12_5H=save(fig,nm)

    # ── Colour palette (matches reference Word document) ─────────────────
    C_NAVY  = colors.HexColor("#1F3B63")   # H1 band, table header, title
    C_BLUE  = colors.HexColor("#2E6CA4")   # subtitle, plot labels
    C_H2    = colors.HexColor("#3F7CB5")   # H2 headings
    C_STRIPE= colors.HexColor("#F4F8FC")   # alternating table rows
    C_GRAY  = colors.HexColor("#555555")   # body/description text
    C_CAP   = colors.HexColor("#5A5A5A")   # captions
    C_FTR   = colors.HexColor("#777777")   # footer text
    C_AMBER = colors.HexColor("#C9962E")   # note boxes
    C_GRNS  = colors.HexColor("#2E7D46")   # insight boxes
    C_GRID  = colors.HexColor("#C8D4E8")   # table grid lines
    HDR = C_NAVY; ALT = C_STRIPE; GRD = C_GRID

    # ── ReportLab styles — Helvetica / 9.5 pt body matching Word doc format ─
    def S(n,**k):
        k.setdefault("fontName","Helvetica"); return ParagraphStyle(n,**k)
    # H1 band: 13 pt bold white (matches Word doc Heading 1 on navy background)
    S_H1W= S("h1w",fontName="Helvetica-Bold",fontSize=13,textColor=colors.white,spaceBefore=0,spaceAfter=0,leading=18)
    # H2: 12 pt bold #3F7CB5 — matches Word doc step sub-section headings (Aptos Display 12 pt)
    S_H2 = S("h2",fontName="Helvetica-Bold",fontSize=12,spaceBefore=10,spaceAfter=5,leading=17,textColor=C_H2)
    # H3: 10 pt bold #3F7CB5
    S_H3 = S("h3",fontName="Helvetica-Bold",fontSize=10,spaceBefore=6,spaceAfter=2,leading=14,textColor=C_H2)
    # Body: 9.5 pt — matches Word doc "Aptos Narrow" 9.5 pt body text
    S_BD = S("bd",fontName="Helvetica",fontSize=9.5,alignment=TA_JUSTIFY,spaceAfter=5,leading=14)
    # Note/caption: 8 pt italic — matches Word doc figure caption style
    S_NT = S("nt",fontName="Helvetica-Oblique",fontSize=8,alignment=TA_JUSTIFY,textColor=C_CAP,spaceAfter=4,leading=12)
    S_CP = S("cp",fontName="Helvetica-Oblique",fontSize=8,alignment=TA_CENTER,textColor=C_CAP,spaceAfter=4,leading=12)
    S_ST = S("st",fontName="Helvetica-Bold",fontSize=9.5,textColor=C_BLUE,spaceBefore=6,spaceAfter=1,leading=14)
    S_KE = S("ke",fontName="Helvetica-Bold",fontSize=11,textColor=C_NAVY,spaceBefore=10,spaceAfter=4,leading=14)
    S_CON= S("con",fontName="Helvetica-Bold",fontSize=9,textColor=C_BLUE,spaceBefore=4,spaceAfter=4,leading=13)
    S_NOB= S("nob",fontName="Helvetica-Bold",fontSize=9.5,textColor=C_AMBER,spaceBefore=4,spaceAfter=4,leading=13)
    S_INS= S("ins",fontName="Helvetica-Bold",fontSize=9,textColor=C_GRNS,spaceBefore=4,spaceAfter=4,leading=13)
    # Cover page styles — 24 pt title / 16 pt subtitle / 12 pt description
    S_CVT= S("cvt",fontName="Helvetica-Bold",fontSize=24,alignment=TA_CENTER,textColor=C_NAVY,spaceAfter=8,leading=30)
    S_CVS= S("cvs",fontName="Helvetica-Bold",fontSize=16,alignment=TA_CENTER,textColor=C_BLUE,spaceAfter=6,leading=22)
    S_CVD= S("cvd",fontName="Helvetica",fontSize=12,alignment=TA_CENTER,textColor=C_GRAY,spaceAfter=4,leading=16)
    S_CVF= S("cvf",fontName="Helvetica-Oblique",fontSize=8.5,alignment=TA_CENTER,textColor=C_FTR,spaceAfter=2,leading=12)

    def P(txt,sty=None): return Paragraph(txt,sty or S_BD)
    # Content width for H1 band — 170 mm A4 content width
    _H1_CW = PAGE_W - LM - RM

    def mkt(data,cw,fs=8.8,hrows=1,lcols=None):
        # Convert inch-based column widths; auto-scale to fit A4 content width
        col_widths = [c*inch for c in cw]
        total = sum(col_widths)
        if total > _H1_CW * 1.005:
            scale = _H1_CW / total
            col_widths = [w * scale for w in col_widths]
        t=Table(data,colWidths=col_widths)
        ts=[("BACKGROUND",(0,0),(-1,hrows-1),HDR),
            ("TEXTCOLOR",(0,0),(-1,hrows-1),colors.white),
            ("FONTNAME",(0,0),(-1,hrows-1),"Helvetica-Bold"),
            ("FONTNAME",(0,hrows),(-1,-1),"Helvetica"),
            ("FONTSIZE",(0,0),(-1,-1),fs),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("ROWBACKGROUNDS",(0,hrows),(-1,-1),[colors.white,ALT]),
            ("GRID",(0,0),(-1,-1),0.4,GRD),
            ("TOPPADDING",(0,0),(-1,-1),3),
            ("BOTTOMPADDING",(0,0),(-1,-1),3)]
        if lcols:
            for c in lcols:
                ts+=[("ALIGN",(c,hrows),(c,-1),"LEFT"),("LEFTPADDING",(c,hrows),(c,-1),6)]
        t.setStyle(TableStyle(ts)); return t

    # Images: sized to A4 content width (170 mm ≈ 6.69 in → use 6.5 in for margin)
    def imgp(pp,w=6.5): return Image(pp,width=w*inch,height=w*0.62*inch)
    def imgf(pp,w=6.5,asp=1.65): return Image(pp,width=w*inch,height=w/asp*inch)
    def sp(h=6): return Spacer(1,h)
    def thr(): return HRFlowable(width="80%",thickness=0.4,color=C_GRID,spaceAfter=3,spaceBefore=3)

    def h1(txt, sb=14, sa=8):
        band = Table([[P(txt, S_H1W)]], colWidths=[_H1_CW])
        band.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),C_NAVY),
            ("TOPPADDING",(0,0),(-1,-1),7),
            ("BOTTOMPADDING",(0,0),(-1,-1),7),
            ("LEFTPADDING",(0,0),(-1,-1),12),
            ("RIGHTPADDING",(0,0),(-1,-1),8),
        ]))
        return [Spacer(1,sb), band, Spacer(1,sa)]

    def on_page(canvas, doc):
        canvas.saveState()
        # Header bar — navy band matching Steps 13-14 style
        canvas.setFillColor(C_NAVY)
        canvas.rect(0, PAGE_H - 13*mm, PAGE_W, 13*mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawString(LM, PAGE_H - 8.5*mm,
            f"{p['topology']}   —   PFC Design Report   —   Steps 1–12")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(PAGE_W - RM, PAGE_H - 8.5*mm, f"Page {doc.page}")
        # Footer rule + centred text
        canvas.setStrokeColor(C_NAVY); canvas.setLineWidth(0.8)
        canvas.line(LM, 7*mm, PAGE_W - RM, 7*mm)
        canvas.setFillColor(C_FTR)
        canvas.setFont("Helvetica", 7.5)
        foot = (f"{p['topology']}   —   PFC Design Report   —   "
                f"Steps 1–12   │   Page {doc.page}")
        canvas.drawCentredString(PAGE_W / 2, 4*mm, foot)
        canvas.restoreState()

    # ── Story ─────────────────────────────────────────────────────────────
    story=[]

    # Cover \u2014 24pt navy title / 16pt blue subtitle / 12pt gray desc (matches reference)
    story+=[
        sp(50),
        P(p["topology"], S_CVT),
        P("PFC Design Report", S_CVS),
        P("Power-Stage and Input-Current Design \u2014 Steps 1 to 12", S_CVD),
        P(f"Continuous-Conduction-Mode Boost   \u2014   Universal Input "
          f"{p['vin_min']:.0f}\u2013{p['vin_max']:.0f} Vac @ {p['f_line']:.0f} Hz   \u2014   "
          f"{p['Pout_low']/1e3:.1f} / {p['Pout_high']/1e3:.1f} kW", S_CVD),
        sp(8),
        HRFlowable(width="100%",thickness=1.2,color=C_NAVY,spaceBefore=6,spaceAfter=6),
        sp(8),]
    story+=[sp(10),P("Generated by PFC AI Agent (Mode B). "
                      "All parameters confirmed during Mode A HITL gate review.",S_NT),PageBreak()]

    # TOC
    story+=[*h1("Table of Contents"),sp(4)]
    story.append(mkt([["Step","Description","Page"],
        ["1","Specification","3"],["2","Input Parameters and Duty Cycle","4"],
        ["3","Ripple Cancellation Factor K(D) at Crest","6"],
        ["4","Calculate L\u03c6 at Low-Line Full Load","7"],
        ["5","Per-Phase RMS Current and Crest Ripple","9"],
        ["6","Plots: Ripple vs. Line Angle","12"],
        ["7","Summary Tables","13"],["8","Worst-Case Line Angle","14"],
        ["9","Results Table","16"],["10","Duty Cycle Waveforms","17"],
        ["11","Per-Phase Current Waveforms","19"],
        ["12","Input Ripple + Signed Ripple + Total Input Current","22"],],
        [0.6,4.8,0.9],fs=10.0))
    story+=[sp(8),PageBreak()]

    # STEP 1
    story+=[*h1("Step 1 \u2014 Specification"),
        P("Design targets confirmed via Mode A HITL gates.",S_BD),sp(4)]
    story.append(mkt([["Parameter","Value"],
        ["Input voltage (Low line)",f"{p['vin_min']:.0f} \u2013 132 Vac @ {p['f_line']:.0f} Hz"],
        ["Input voltage (High line)",f"180 \u2013 {p['vin_max']:.0f} Vac @ {p['f_line']:.0f} Hz"],
        ["Output voltage",f"{p['Vout']:.1f} Vdc"],
        ["Output power (Low line)",f"{p['Pout_low']:.0f} W"],
        ["Output power (High line)",f"{p['Pout_high']:.0f} W"],
        ["Switching frequency",f"{p['fsw']/1e3:.0f} kHz"],
        ["DC bus ripple pk-pk",f"{p['Vripple']:.0f} V"],
        ["Input ripple ratio at crest",f"{p['r_input']*100:.1f} %"],
        ["Interleaved phases",str(p['N_phases'])],
        ["Controller mode",p['ctrl_mode'].title()],
        ["Switch technology",p['sw_tech']],
        ["Cooling",p['cooling']],],
        [2.7,3.6],fs=9.8,lcols=[0]))
    story+=[sp(10),P("Operating points (efficiency and power factor per Vin/Pout):",S_BD),sp(4)]
    story.append(mkt([["Vin_rms (Vac)","Pout (W)","eta","PF"]]+
        [[f"{int(Vin_rms[i])}",f"{int(Pout[i])}",f"{eta[i]:.3f}",f"{PF[i]:.4f}"]
         for i in range(n)],[1.5,1.5,1.2,1.3],fs=9.8))
    story+=[PageBreak()]

    # STEP 2
    story+=[*h1("Step 2 \u2014 Calculate Input Parameters and Duty Cycle"),sp(4)]
    for lbl,ltx,fs,num in[
        ("Step A",r"$P_{\rm in}=P_{\rm out}/\eta$",20,"(A)"),
        ("Step B",r"$V_{\rm in,pk}=\sqrt{2}\cdot V_{\rm in,rms}$",19,"(B)"),
        ("Step C",r"$I_{\rm in,rms}=P_{\rm in}/(V_{\rm in,rms}\cdot{\rm PF})$",18,"(C)"),
        ("Step D",r"$I_{\rm in,pk}=\sqrt{2}\cdot I_{\rm in,rms}$",19,"(D)"),
        ("Step E",r"$D_{\rm pk}=1-V_{\rm in,pk}/V_{\rm out}$",18,"(E)"),
    ]:
        story+=[P(lbl,S_ST)]+render_eq(ltx,fs,num)+[thr()]
    story+=[sp(8)]
    story.append(mkt([["Vin_rms\n(Vac)","Vin_pk\n(V)","Dpk","Pout\n(W)","eta","PF",
                        "Pin\n(W)","Iin_rms\n(A)","Iin_pk\n(A)"]]+
        [[f"{int(Vin_rms[i])}",f"{Vin_pk[i]:.3f}",f"{Dpk[i]:.6f}",
          f"{int(Pout[i])}",f"{eta[i]:.3f}",f"{PF[i]:.4f}",
          f"{Pin[i]:.3f}",f"{Iin_rms[i]:.3f}",f"{Iin_pk[i]:.3f}"]
         for i in range(n)],[0.67,0.78,0.84,0.65,0.58,0.73,0.83,0.80,0.78],fs=8.2))
    story+=[sp(10),P("Vin_rms vs Duty at Crest",S_CP),imgp(p_dpk,6.1),PageBreak()]

    # STEP 3
    story+=[*h1("Step 3 \u2014 Ripple Cancellation Factor K(D) at Crest"),sp(4),
        P("The two-phase interleaved boost cancels input ripple by factor K(D):",S_BD),sp(4)]
    for lbl,ltx,fs,num in[
        ("D < 0.5",r"$K(D)=(1-2D)/(1-D)$",20,"(2)"),
        ("D > 0.5",r"$K(D)=(2D-1)/D$",20,"(3)"),
        ("D = 0.5",r"$K(D)=0\;\text{(complete cancellation)}$",20,"(4)"),
    ]:
        story+=[P(lbl,S_ST)]+render_eq(ltx,fs,num)+[thr()]
    story+=[sp(8)]
    story.append(mkt([["Vin_rms (Vac)","Vin_pk (V)","Dpk","K(Dpk)"]]+
        [[f"{int(Vin_rms[i])}",f"{Vin_pk[i]:.3f}",f"{Dpk[i]:.6f}",f"{KDpk[i]:.6f}"]
         for i in range(n)],[1.6,1.6,1.6,1.6],fs=9.8))
    story+=[sp(8),P("K(D) vs Duty",S_CP),imgp(p_KD,6.1),sp(4),
            P("K(Dpk) vs Vin_rms",S_CP),imgp(p_KDv,6.1),PageBreak()]

    # STEP 4
    ref=s4["ref_idx"]
    story+=[*h1("Step 4 \u2014 Calculate L\u03c6 at Low-Line Full Load"),sp(4),
        P(f"Sized at {int(Vin_rms[ref])} Vac, V<sub>out</sub>={p['Vout']:.1f} Vdc, "
          f"f<sub>sw</sub>={p['fsw']/1e3:.0f} kHz, r={p['r_input']*100:.1f} %.",S_BD),sp(4)]
    for lbl,ltx,fs,num in[
        ("",r"$\Delta I_{\rm in,pp}=r\cdot I_{\rm in,pk}="+
           f"{p['r_input']}\times{Iin_pk[ref]:.4f}={s4['dIin_ref']:.4f}"+r"\ \rm A$",17,"(4.1)"),
        ("",r"$\Delta I_{L,pp}=\Delta I_{\rm in,pp}/K="+
           f"{s4['dIin_ref']:.4f}/{KDpk[ref]:.6f}={s4['dIL_ref']:.4f}"+r"\ \rm A$",17,"(4.2)"),
        ("",r"$L_\phi=V_{\rm in,pk}\cdot D_{\rm pk}/(\Delta I_{L,pp}\cdot f_{\rm sw})="+
           f"{L_phi_calc*1e6:.2f}"+r"\ \mu\rm H$",16,"(4.3)"),
    ]:
        story+=render_eq(ltx,fs,num)+[thr()]
    story+=[sp(6)]
    story.append(mkt([["Quantity","Value"],
        ["Vin_pk",f"{Vin_pk[ref]:.4f} V"],["Dpk",f"{Dpk[ref]:.6f}"],
        ["dIin_pp",f"{s4['dIin_ref']:.4f} A"],["K(Dpk)",f"{KDpk[ref]:.6f}"],
        ["dIL_pp",f"{s4['dIL_ref']:.4f} A"],
        ["Computed L_phi",f"{L_phi_calc*1e6:.2f} \u00b5H"],
        ["Selected L_phi",f"{L_phi*1e6:.0f} \u00b5H"],],
        [3.1,3.2],fs=9.8,lcols=[0]))
    story+=[PageBreak()]

    # STEP 5
    story+=[*h1("Step 5 \u2014 Per-Phase RMS Current and Crest Ripple Results"),sp(4),
        P(f"Numerical integration, L\u03c6 = {L_phi*1e6:.0f} \u00b5H.",S_BD),sp(4)]
    for lbl,ltx,fs,num in[
        ("Average per-phase current:",
         r"$i_{L,\rm avg,\phi}(\theta)=\frac{I_{\rm in,pk}}{2}\sin\theta$",18,"(5.1)"),
        ("Total per-phase RMS:",
         r"$I_{L,\phi,\rm rms}=\sqrt{\frac{1}{\pi}\int_0^{\pi}[i_{L,\rm avg}^2+i_{L,\rm hf}^2]\,d\theta}$",16,"(5.2)"),
    ]:
        story+=[P(lbl,S_ST)]+render_eq(ltx,fs,num)+[thr()]
    story+=[sp(8),P("Table 5.1 \u2014 Input current and ripple at crest:",S_H2),sp(4)]
    story.append(mkt([["Vin_rms\n(Vac)","Iin_rms\n(A)","Iin_pk\n(A)",
                        "dIin_pp@crest\n(A)","I_in,pk@crest\nw/ Ripple (A)"]]+
        [[f"{int(Vin_rms[i])}",f"{Iin_rms[i]:.3f}",f"{Iin_pk[i]:.3f}",
          f"{dIin_crest[i]:.3f}",f"{Iph_pk[i]:.3f}"] for i in range(n)],
        [1.2,1.3,1.2,1.7,1.9],fs=9.2))
    story+=[sp(10),P("Table 5.2 \u2014 Inductor current RMS per phase:",S_H2),sp(4)]
    story.append(mkt([["Vin_rms\n(Vac)","Iin_rms\n(A)","IL_φ,rms\n(A)",
                        "IL_φ,rms LF\n(A)","IL_φ,rms HF\n(A)","dIL_pp\n@crest (A)",
                        "I_L,φ,pk\n@crest (A)"]]+
        [[f"{int(Vin_rms[i])}",f"{Iin_rms[i]:.3f}",f"{IL_rms[i]:.4f}",
          f"{IL_LF[i]:.4f}",f"{IL_HF[i]:.4f}",f"{dIL_crest[i]:.4f}",
          f"{Iph_pk[i]:.4f}"] for i in range(n)],
        [0.9,1.0,1.1,1.1,1.1,1.2,1.3],fs=8.8))
    story+=[sp(10),
        P("IL_phi_rms vs Vin_rms",S_CP),imgp(p_ilrms),sp(4),
        P("Iin_rms vs Vin_rms",S_CP),imgp(p_iinrms),sp(4),PageBreak(),
        P("Iin_pk vs Vin_rms",S_CP),imgp(p_iinpk),sp(4),
        P("dIin_pp@crest vs Vin_rms",S_CP),imgp(p_diin),PageBreak()]

    # STEP 6
    story+=[*h1("Step 6 \u2014 Plots: Ripple vs. Line Angle"),sp(4),
        P("Per-phase inductor ripple plotted vs line angle for all 9 operating points.",S_BD),sp(6),
        P("Plot A \u2014 0\u00b0 to 90\u00b0",S_CP),imgf(p6a),
        P("Per-phase ripple from zero-crossing to the crest.",S_NT),sp(4),
        P("Plot B \u2014 0\u00b0 to 180\u00b0",S_CP),imgf(p6b),
        P("Full half cycle. High-line curves show characteristic twin peaks.",S_NT),sp(4),
        P("Plot C \u2014 High-line zoom (worst-case point marked)",S_CP),imgf(p6c),
        P("High-line family: every curve touches the maximum ripple ceiling at Vin = Vout/2.",S_NT),
        sp(4),PageBreak(),
        P("Plot D \u2014 Input ripple envelope after K(D) interleaved cancellation",S_CP),
        Image(p6d,width=6.5*inch,height=7.8*inch),
        P("Input ripple \u0394I<sub>in,pp</sub>(\u03b8) = K(D(\u03b8))\u00b7\u0394I<sub>L,pp</sub>(\u03b8) "
          "for low-line (top) and high-line (bottom). "
          "Cancellation zeros the envelope near D = 0.5 (132 Vac).",S_NT)]

    # STEP 7
    story+=[*h1("Step 7 \u2014 Summary Tables"),sp(4),
            P("Table 7.1 \u2014 Crest-of-line ripple and currents:",S_H2),sp(4)]
    story.append(mkt([["Vin\n(V)","eta","Pout\n(W)","Pin\n(W)","Iin_rms\n(A)","Iin_pk\n(A)",
                        "Vpk\n(V)","D@crest","dIL_pp\n(A)","dIin_pp\n(A)","dIin/Ipk\n%","Iph_pk\n(A)","<15%\nPass?"]]+
        [[f"{int(Vin_rms[i])}",f"{eta[i]:.3f}",f"{int(Pout[i])}",f"{Pin[i]:.2f}",
          f"{Iin_rms[i]:.3f}",f"{Iin_pk[i]:.3f}",f"{Vin_pk[i]:.3f}",f"{Dpk[i]:.4f}",
          f"{dIL_crest[i]:.4f}",f"{dIin_crest[i]:.4f}",f"{r_act[i]*100:.2f}",
          f"{Iph_pk[i]:.4f}","YES"] for i in range(n)],
        [0.42,0.35,0.42,0.54,0.52,0.52,0.52,0.46,0.53,0.53,0.49,0.55,0.38],fs=7.0))
    story+=[sp(10),P("Table 7.2 \u2014 Worst-case line angle:",S_H2),sp(4)]
    story.append(mkt([["Vin\n(V)","Vpk\n(V)","Vin@max\n(V)","theta1\n(deg)",
                        "t1\n(ms)","D_worst","dIL_max\n(A)","Condition"]]+
        [[f"{int(Vin_rms[i])}",f"{Vin_pk[i]:.3f}",f"{Vin_w[i]:.4f}",
          f"{np.degrees(th1[i]):.4f}",f"{t1_ms[i]:.4f}",f"{D_w[i]:.4f}",
          f"{dIL_max[i]:.4f}",
          "Vpk<Vout/2 crest" if Vin_pk[i]<p["Vout"]/2 else "Vin=Vout/2"]
         for i in range(n)],
        [0.43,0.57,0.62,0.66,0.60,0.62,0.62,1.51],fs=7.5,lcols=[7]))
    story+=[PageBreak()]

    # STEP 8
    story+=[*h1("Step 8 \u2014 Worst-Case Line Angle for Maximum Per-Phase Ripple"),sp(4)]
    for lbl,ltx,fs,num in[
        ("Step 8.1",r"$\Delta I_{L,pp}(\theta)=V_{\rm in}(\theta)\cdot D(\theta)/(L_\phi\cdot f_{\rm sw})$",17,"(8.1)"),
        ("Step 8.2",r"$dg/dV_{\rm in}=0\;\Rightarrow\;V_{\rm in}=V_{\rm out}/2="+
                    f"{p['Vout']/2:.1f}"+r"\ \rm V$",16,"(8.2)"),
        ("Step 8.3",r"$\theta_1=\arcsin(V_{\rm out}/(2V_{\rm pk}))\;,\quad\theta_2=180°-\theta_1$",15,"(8.3)"),
    ]:
        story+=[P(lbl,S_ST)]+render_eq(ltx,fs,num)+[thr()]
    story+=[sp(8),P("Worst-case angle vs Vin_rms",S_CP),imgp(p8a),sp(4),
            P("dIL_pp_max vs Vin_rms",S_CP),imgp(p8b),PageBreak()]

    # STEP 9
    story+=[*h1("Step 9 \u2014 Results Table"),sp(4)]
    story.append(mkt([["Vin_rms\n(Vac)","Vin_pk\n(V)","Vin@max\n(V)","theta1\n(deg)","t1\n(ms)",
                        "theta2\n(deg)","t2\n(ms)","dIL_max\n(A)","Condition"]]+
        [[f"{int(Vin_rms[i])}",f"{Vin_pk[i]:.4f}",f"{Vin_w[i]:.4f}",
          f"{np.degrees(th1[i]):.4f}",f"{t1_ms[i]:.4f}",
          f"{np.degrees(th2[i]):.4f}",f"{t2_ms[i]:.4f}",f"{dIL_max[i]:.4f}",
          "Vpk<Vout/2 -> crest" if Vin_pk[i]<p["Vout"]/2 else "Vin=Vout/2 reachable"]
         for i in range(n)],
        [0.62,0.68,0.68,0.68,0.63,0.68,0.63,0.76,1.59],fs=8.0,lcols=[8]))
    story+=[sp(8),
        P(f"\u0394I<sub>L,pp,max</sub> = {dIL_max_global:.4f} A at D = 0.5 "
          f"(V<sub>in</sub> = V<sub>out</sub>/2 = {p['Vout']/2:.1f} V).",S_NT),PageBreak()]

    # STEP 10
    story+=[*h1("Step 10 \u2014 Duty Cycle Waveforms"),sp(4),
        P(f"D(t) = 1 \u2212 V<sub>in,pk</sub>|sin(2\u03c0f<sub>line</sub>t)| / V<sub>out</sub>. "
          "Red dashed: D<sub>pk</sub>.",S_BD),sp(6)]
    for i2,pp in enumerate(p10):
        story+=[P(f"Group {i2+1}",S_CP),Image(pp,width=6.5*inch,height=3.0*inch),sp(4)]
    # Compact ripple table
    story+=[sp(6),P("Compact Crest-of-Line Ripple Table",S_H2),sp(4)]
    story.append(mkt([["Vac_rms\n(V)","eta","D@crest","K(D)@crest","dIL_pp@crest\n(A)",
                        "dIin_pp@crest\n(A)","dIin/Ipk\n@crest","15% pass?"]]+
        [[f"{int(Vin_rms[i])}",f"{eta[i]:.3f}",f"{Dpk[i]:.4f}",f"{KDpk[i]:.4f}",
          f"{dIL_crest[i]:.4f}",f"{dIin_crest[i]:.4f}",f"{r_act[i]*100:.3f}%","YES"]
         for i in range(n)],[0.65,0.52,0.72,0.78,0.92,0.92,0.82,0.72],fs=8.8))
    story+=[PageBreak()]

    # STEP 11
    story+=[*h1("Step 11 \u2014 Per-Phase Current Waveforms"),sp(4),
        P(f"Phase A shown. Phase B identical average, T<sub>s</sub>/2 shifted. "
          f"L\u03c6 = {L_phi*1e6:.0f} \u00b5H, f<sub>sw</sub> = {p['fsw']/1e3:.0f} kHz.",S_BD),sp(4),
        P("Key equations:",S_KE)]
    for ltx,fs,num in[
        (r"$V_{\rm pk}=\sqrt{2}\cdot V_{\rm in,rms}\;,\quad D(\theta)=1-V_{\rm in}(\theta)/V_{\rm out}$",15,"(11.1)"),
        (r"$\Delta I_{L,pp}(\theta)=V_{\rm in}\cdot D/(L_\phi f_{\rm sw})$",17,"(11.2)"),
        (r"$i_{L,\rm avg,\phi}(t)=\frac{1}{2}I_{\rm in,pk}\sin(2\pi f_{\rm line}t)$",17,"(11.3)"),
        (r"$i_{L\phi,A}(t)=i_{L,\rm avg,\phi}(t)+\tilde{i}_{L\phi,A}(t)\;,\quad \tilde{i}_{L\phi,B}(t)=\tilde{i}_{L\phi,A}(t+T_s/2)$",14,"(11.4)"),
    ]:
        story+=render_eq(ltx,fs,num)+[thr()]
    _FULL_H = 7.8*inch   # full-page double-panel height on A4
    story+=[sp(8),P("Step 11.1 \u2014 Ripple envelope over half cycle",S_H2),sp(4),
        Image(p11_1,width=6.5*inch,height=_FULL_H),sp(4),PageBreak(),
        P("Step 11.2 \u2014 Signed ripple (Phase A) \u2014 Low line",S_H2),sp(4),
        imgf(p11_2),sp(4),
        P("Step 11.3 \u2014 Signed ripple (Phase A) \u2014 High line",S_H2),sp(4),
        imgf(p11_3),PageBreak(),
        P("Step 11.4 \u2014 Per-phase current over half cycle",S_H2),sp(4),
        Image(p11_4,width=6.5*inch,height=_FULL_H),PageBreak(),
        P("Step 11.5 \u2014 Switching ripple around crest \u2014 Low line",S_H2),sp(4),
        imgf(p11_5L),sp(4),
        P("Step 11.5 \u2014 Switching ripple around crest \u2014 High line",S_H2),sp(4),
        imgf(p11_5H),PageBreak(),
        P("Step 11.6 \u2014 Phase A vs Phase B",S_H2),sp(4),
        imgf(p11_6),PageBreak()]

    # STEP 12
    story+=[*h1("Step 12 \u2014 Input Ripple, Signed Ripple, and Total Input Current"),sp(4),
        P("i<sub>in,total</sub>(t) = i<sub>in,avg</sub>(t) + delta_iin(t).",S_BD),sp(4),
        P("Key equations (all Step 11 equations plus):",S_KE)]
    for ltx,fs,num in[
        (r"$\Delta I_{\rm in,pp}(\theta)=K(D(\theta))\cdot\Delta I_{L,pp}(\theta)$",17,"(12.1)"),
        (r"$\delta i_{\rm in}(t)=\tilde{i}_{L\phi,A}(t)+\tilde{i}_{L\phi,B}(t)$",17,"(12.2)"),
        (r"$i_{\rm in,total}(t)=I_{\rm in,pk}\sin(2\pi f_{\rm line}t)+\delta i_{\rm in}(t)$",15,"(12.3)"),
    ]:
        story+=render_eq(ltx,fs,num)+[thr()]
    story+=[sp(8),P("Step 12.1 \u2014 Input ripple envelope over half cycle",S_H2),sp(4),
        Image(p12_1,width=6.5*inch,height=_FULL_H),PageBreak(),
        P("Step 12.2 \u2014 Signed input ripple \u2014 Low line",S_H2),sp(4),
        imgf(p12_2),sp(4),
        P("Step 12.3 \u2014 Signed input ripple \u2014 High line",S_H2),sp(4),
        imgf(p12_3),PageBreak(),
        P("Step 12.4 \u2014 Total input current over half cycle",S_H2),sp(4),
        Image(p12_4,width=6.5*inch,height=_FULL_H),PageBreak(),
        P("Step 12.5 \u2014 Switching ripple around crest \u2014 Low line",S_H2),sp(4),
        imgf(p12_5L),sp(4),
        P("Step 12.5 \u2014 Switching ripple around crest \u2014 High line",S_H2),sp(4),
        imgf(p12_5H)]

    # Build PDF \u2014 A4, 20 mm margins, matching Steps 13\u201315 layout
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=LM, rightMargin=RM,
        topMargin=TM, bottomMargin=BM,
        title=f"PFC Design Report \u2014 {p['topology']}",
        author="PFC AI Agent (Mode B)")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
