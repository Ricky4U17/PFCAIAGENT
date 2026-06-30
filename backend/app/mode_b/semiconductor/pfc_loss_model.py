"""
Interleaved CCM/DCM PFC -- semiconductor + thermal loss engine
==============================================================
SCOPE: bridge rectifier, boost MOSFET(s) (Si or SiC), boost diode, and their thermals ONLY.
       No inductor or output-capacitor loss is computed here (by design).

Operating point: efficiency (eta) and power factor (PF) are SUPPLIED by the designer at each
input voltage (no eta iteration). The line current follows directly from eta and PF; only the
junction temperatures are iterated (Rds(on), Vf, Qrr, switching energy are Tj-dependent).

Because eta is supplied, total system loss is known (Po*(1-eta)/eta). The engine reports the
semiconductor share it computes and the implied non-semiconductor remainder as a cross-check.

Fidelity (all opt-in; defaults reproduce the validated baseline):
  MOSFET : Eon/Eoff(Tj) (tempco or 2-temperature curves), two-point Crss integral, loop/pkg
           inductance, split Rg(on/off), Vpl(I), Rdson(Id,Tj), leakage, Zth peaks, tolerances.
           Coss is handled as TWO distinct mechanisms: (a) Eoss is fully dissipated at the hard
           turn-on into Vo (P_oss, always full); (b) the turn-OFF crossover gets a snubber CREDIT
           via k_turnoff (0.5..1.0) because Coss diverts current during the voltage rise.
  DIODE  : Qrr(If, di/dt, Tj) for Si with user-set FET/diode recovery-energy partition, SiC Qc,
           forward-recovery energy, Vf(I,Tj), leakage, Zth, tolerances.
  BRIDGE : plain (N-parallel) or sync-bottom (top diode + bottom MOSFET); Vf(I,Tj); bottom
           Rdson(Tj) + bottom-MOSFET gate loss (line-freq) + its own thermal node; tolerances.
  THERMAL: per-device case nodes; optional separate heatsink for the bridge; transient Zth.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

def curve(x, xs, ys):
    return np.interp(x, np.asarray(xs, float), np.asarray(ys, float))
SQRT2 = np.sqrt(2.0)

def transient_tj(p_theta, fline, foster, t_case, periods=12, span=None):
    # span = real-time duration of the supplied waveform; FET/diode/bridge devices that
    # dissipate on every half line cycle use 1/(2*fline) (the default).
    if not foster: return None
    half = span if span is not None else 1.0/(2.0*fline); n = len(p_theta); dt = half/n
    p = np.tile(p_theta, periods); T = np.zeros(len(foster)); tr = np.empty(len(p))
    for k in range(len(p)):
        pk = p[k]
        for i,(R,tau) in enumerate(foster): T[i] += dt/tau*(R*pk - T[i])
        tr[k] = t_case + T.sum()
    tail = tr[-n:]; return float(tail.max()), float(tail.mean()), float(tail.max()-tail.min())

# ======================================================================================
@dataclass
class Mosfet:
    tech: str = "si"
    rdson_25: float = 0.045
    rdson_tj: Optional[tuple] = None
    rdson_id_curve: Optional[tuple] = None
    sw_method: str = "analytic"
    ciss: float = 4340e-12; qgd: float = 30e-9
    crss_curve: Optional[tuple] = None
    vth: float = 3.5; vpl: float = 5.4; gfs: Optional[float] = None
    vg: float = 12.0; rg: float = 1.8; rg_on: Optional[float] = None; rg_off: Optional[float] = None
    k_turnoff: float = 1.0; ls_loop: float = 0.0
    eon_curve: tuple = ((1.0,10.0),(5e-6,50e-6)); eoff_curve: tuple = ((1.0,10.0),(10e-6,80e-6))
    vref_sw: float = 400.0
    eon_curve_hot: Optional[tuple] = None; eoff_curve_hot: Optional[tuple] = None
    tj_ref_sw: float = 25.0; tj_hot_sw: float = 125.0
    esw_tco: float = 0.0                       # fractional dEsw/dTj if no hot curves (e.g. 0.004 = 0.4%/C)
    eoss_at_v: tuple = ((100.0,400.0),(3e-6,11.7e-6))
    qg: float = 93e-9; vg_drive: float = 12.0
    idss_curve: Optional[tuple] = None
    vsd: float = 0.0; qrr_body: float = 0.0
    rth_jc: float = 0.29; rth_cs: float = 0.5
    zth_foster: list = field(default_factory=list)
    # tolerance multipliers (1.0 = typical; set >1 for worst-case signoff)
    k_rdson: float = 1.0; k_esw: float = 1.0; k_coss: float = 1.0; k_qg: float = 1.0

    def _tjcoef(self):
        if self.rdson_tj is not None: return self.rdson_tj
        return ((25,100),(1.0,1.8)) if self.tech=="si" else ((25,125),(1.0,1.4))
    def rdson(self, Tj, Id=None):
        r = self.rdson_25*curve(Tj,*self._tjcoef())*self.k_rdson
        if self.rdson_id_curve is not None and Id is not None: r *= curve(Id,*self.rdson_id_curve)
        return r
    def eoss(self, Vo): return curve(Vo,*self.eoss_at_v)*self.k_coss
    def _rg(self, on): return (self.rg_on or self.rg) if on else (self.rg_off or self.rg)
    def _vpl(self, i): return self.vpl if self.gfs is None else (self.vth+np.asarray(i)/self.gfs)
    def _Jvcrss(self, Vo):
        if self.crss_curve is None: return self.qgd*Vo/2.0
        vs = np.linspace(Vo*1e-3, Vo, 256); y = vs*curve(vs,*self.crss_curve)
        integ = np.trapezoid if hasattr(np,'trapezoid') else np.trapz   # numpy<2 portability
        return float(integ(y, vs))
    def _t_current(self, vpl, rg, rising):
        return self.ciss*rg*np.log((self.vg-self.vth)/(self.vg-vpl)) if rising else self.ciss*rg*np.log(vpl/self.vth)
    def _esw_tj_factor(self, Tj):                  # temperature scaling of switching energy
        return 1.0 + self.esw_tco*(Tj - self.tj_ref_sw)
    def _esw_curves(self, i, Tj, on):
        base, hot = (self.eon_curve, self.eon_curve_hot) if on else (self.eoff_curve, self.eoff_curve_hot)
        e_cold = curve(i, *base)
        if hot is None: return e_cold                       # tempco applied separately
        e_hot = curve(i, *hot)
        f = np.clip((Tj-self.tj_ref_sw)/(self.tj_hot_sw-self.tj_ref_sw), 0, None)
        return e_cold + (e_hot-e_cold)*f                    # linear in Tj between the two curves

    def e_switch(self, i_on, i_off, Vo, Tj):
        i_on = np.maximum(i_on,0.0); i_off = np.maximum(i_off,0.0)
        if self.sw_method == "esw":
            s = Vo/self.vref_sw
            e_on = self._esw_curves(i_on, Tj, True)*s
            e_off = self._esw_curves(i_off, Tj, False)*s*self.k_turnoff
            if self.eon_curve_hot is None: e_on *= self._esw_tj_factor(Tj)
            if self.eoff_curve_hot is None: e_off *= self._esw_tj_factor(Tj)
        else:
            ron, roff = self._rg(True), self._rg(False)
            vpl_on = np.maximum(self._vpl(i_on), self.vth+0.1); vpl_off = np.maximum(self._vpl(i_off), self.vth+0.1)
            J = self._Jvcrss(Vo); Ig_on = (self.vg-vpl_on)/ron; Ig_off = vpl_off/roff
            t_ir = self._t_current(vpl_on, ron, True); t_if = self._t_current(vpl_off, roff, False)
            e_on = (0.5*Vo*i_on*t_ir + i_on*J/Ig_on)*self._esw_tj_factor(Tj)
            e_off = (i_off*J/Ig_off + 0.5*Vo*i_off*t_if)*self.k_turnoff*self._esw_tj_factor(Tj)
        e_off = e_off + 0.5*self.ls_loop*i_off**2
        return (e_on + e_off)*self.k_esw
    def didt(self, i_off, Vo):
        vpl = np.maximum(self._vpl(i_off), self.vth+0.1)
        return i_off/np.maximum(self._t_current(vpl, self._rg(True), True), 1e-12)
    def p_leak(self, Vo, Tj, off_duty):
        return 0.0 if self.idss_curve is None else Vo*curve(Tj,*self.idss_curve)*off_duty

# ======================================================================================
@dataclass
class Diode:
    vf_curve: tuple = ((1.0,3.0,12.0,24.0),(1.15,1.35,1.6,1.9))
    vf_tco: float = 0.0; vf_tref: float = 25.0
    rd: float = 0.0
    is_sic: bool = True
    qc: float = 23e-9
    qrr: float = 0.0
    qrr_didt_curve: Optional[tuple] = None
    qrr_if_curve: Optional[tuple] = None        # (If[A], Qrr/Qrr_ref) multiplier
    qrr_tco: float = 0.0
    rr_fet_frac: float = 0.85                   # recovery energy partition: fraction into FET
    e_fr: float = 0.0
    irev_curve: Optional[tuple] = None
    rth_jc: float = 0.8; rth_cs: float = 0.5
    zth_foster: list = field(default_factory=list)
    k_vf: float = 1.0; k_qrr: float = 1.0; k_qc: float = 1.0
    def vf(self, i, Tj=25.0):
        return (curve(np.maximum(i,0.0),*self.vf_curve) + self.vf_tco*(Tj-self.vf_tref))*self.k_vf
    def qrr_eff(self, If, didt, Tj):
        if self.is_sic: return self.qc*self.k_qc
        q = curve(didt,*self.qrr_didt_curve) if self.qrr_didt_curve is not None else self.qrr
        if self.qrr_if_curve is not None: q = q*curve(If,*self.qrr_if_curve)
        return q*(1.0+self.qrr_tco*(Tj-25.0))*self.k_qrr

# ======================================================================================
@dataclass
class Bridge:
    topology: str = "diode"
    vf_curve: tuple = ((1.0,10.0,25.0),(0.8,1.0,1.2))
    vf_tco: float = 0.0; vf_tref: float = 25.0; rd: float = 0.0
    n_parallel: int = 1; n_parallel_top: int = 1; n_parallel_bottom: int = 1
    rdson_bottom_25: float = 0.020; rdson_bottom_tj: tuple = ((25,125),(1.0,1.5))
    qg_bottom: float = 0.0; vg_bottom: float = 12.0          # bottom sync-FET gate (line-freq)
    qrr: float = 0.0
    rth_jc: float = 1.0; rth_cs: float = 0.5
    rth_jc_bottom: float = 0.8; rth_cs_bottom: float = 0.5
    zth_foster: list = field(default_factory=list)
    k_vf: float = 1.0; k_rdson: float = 1.0
    def vf(self, i, Tj=25.0):
        return (curve(np.maximum(i,0.0),*self.vf_curve) + self.vf_tco*(Tj-self.vf_tref))*self.k_vf
    def loss(self, i_in, Tj_top, Tj_bot, fline, Vpk):
        mean = lambda a: float(np.mean(a))
        # Optional line-frequency bridge recovery. Normally NEGLIGIBLE vs the switching stage and
        # independent of current waveform -- a placeholder, not a high-fidelity recovery model.
        rr = 2.0*self.qrr*Vpk*(2.0*fline)
        if self.topology == "sync_bottom":
            it = i_in/self.n_parallel_top
            rb = self.rdson_bottom_25*curve(Tj_bot,*self.rdson_bottom_tj)*self.k_rdson/self.n_parallel_bottom
            top = mean(self.vf(it,Tj_top)*i_in + (self.rd/self.n_parallel_top)*i_in**2)
            bot = mean(rb*i_in**2)
            gate_bot = self.qg_bottom*self.vg_bottom*2.0*fline*self.n_parallel_bottom
            return {"total": top+bot+gate_bot+rr, "top": top+rr, "bottom": bot+gate_bot,
                    "ndev_top": self.n_parallel_top, "ndev_bot": self.n_parallel_bottom}
        idev = i_in/self.n_parallel
        tot = 2.0*mean(self.vf(idev,Tj_top)*i_in + (self.rd/self.n_parallel)*i_in**2) + rr
        return {"total": tot, "top": tot, "bottom": 0.0, "ndev_top": 2*self.n_parallel, "ndev_bot": 0}
    def power_theta(self, i_in, Tj_top, Tj_bot):
        """Per-device instantaneous power shape vs line angle (for transient Tj). Scaled to the
        per-device average by the caller, so duty bookkeeping stays consistent with loss()."""
        if self.topology == "sync_bottom":
            it = i_in/self.n_parallel_top
            rb = self.rdson_bottom_25*curve(Tj_bot,*self.rdson_bottom_tj)*self.k_rdson
            p_top = self.vf(it,Tj_top)*it + self.rd*it**2
            p_bot = rb*(i_in/self.n_parallel_bottom)**2
            return p_top, p_bot
        idev = i_in/self.n_parallel
        return self.vf(idev,Tj_top)*idev + self.rd*idev**2, None

@dataclass
class Thermal:
    t_ambient: float = 40.0
    rth_sa: float = 0.5                      # main sink (MOSFET + boost diode)
    t_sink_fixed: Optional[float] = None
    separate_bridge_sink: bool = False
    rth_sa_bridge: float = 0.8               # bridge's own sink (if separate)
    t_sink_bridge_fixed: Optional[float] = None

@dataclass
class Spec:
    vo: float = 400.0; po: float = 1200.0; fsw: float = 100e3
    fline: float = 60.0; nch: int = 1; n_theta: int = 600; L: float = 168.5e-6
    eta: float = 0.95; pf: float = 0.99
    eta_curve: Optional[tuple] = None        # (Vac, eta) supplied by designer
    pf_curve: Optional[tuple] = None         # (Vac, PF) supplied by designer
    po_curve: Optional[tuple] = None         # (Vac, Po) -> output power may differ low/high line
    cout: float = 0.0                        # output bulk capacitance [F] (ripple check only; not a loss)
    # ---- OPERATING POINT SUPPLIED BY AN UPSTREAM SCRIPT (all optional; 0/None = "compute it") ----
    # Provide any of these and the engine uses them verbatim instead of deriving them, so this
    # module can drop into a larger tool that already knows Vac, Pin, Iin, L, ripple, PF and eta.
    # Precedence for the line current:  iin_rms(_curve)  >  pin(_curve)/(Vac*PF)  >  Po/(eta*Vac*PF).
    pin: float = 0.0                         # total input power [W]            (0 = not supplied)
    pin_curve: Optional[tuple] = None        # (Vac, Pin)
    iin_rms: float = 0.0                     # total input RMS current [A]      (0 = not supplied)
    iin_rms_curve: Optional[tuple] = None    # (Vac, Iin_rms)
    pct_ripple: float = 0.0                  # peak-of-line inductor ripple as a FRACTION of peak
                                             #   channel current (e.g. 0.25). 0 = use L instead.
    di_pp_peak: float = 0.0                  # OR the peak-of-line ripple current directly [A pp]
    di_pp_peak_curve: Optional[tuple] = None # (Vac, di_pp_peak)

# ======================================================================================
def simulate_point(vac, sp, mos, dio, br, th, return_waveforms=False, return_trace=False):
    Vo, fsw, Nch = sp.vo, sp.fsw, sp.nch
    Po  = float(curve(vac, *sp.po_curve)) if sp.po_curve else sp.po
    eta = float(curve(vac, *sp.eta_curve)) if sp.eta_curve else sp.eta
    pf  = float(curve(vac, *sp.pf_curve)) if sp.pf_curve else sp.pf
    # ---- input power / current: use upstream-supplied values when given (see Spec for precedence) ----
    Pin = float(curve(vac, *sp.pin_curve)) if sp.pin_curve else (sp.pin or 0.0)
    if Pin > 0:
        Po = eta*Pin                                   # supplied input power -> output power via eta
    if sp.iin_rms_curve:   Iin_rms = float(curve(vac, *sp.iin_rms_curve))
    elif sp.iin_rms > 0:   Iin_rms = sp.iin_rms
    elif Pin > 0:          Iin_rms = Pin/(vac*pf)
    else:                  Iin_rms = Po/(eta*vac*pf)
    if Pin <= 0:           Pin = Po/eta                 # keep Pin defined for reporting
    Vpk = SQRT2*vac
    theta = np.linspace(1e-4, np.pi-1e-4, sp.n_theta); sint = np.sin(theta)
    vin = Vpk*sint; d = np.clip(1.0-vin/Vo, 0.0, 1.0); avg = lambda a: float(np.mean(a))
    Ipk_ch = SQRT2*Iin_rms/Nch
    i_ch = Ipk_ch*sint; i_in = SQRT2*Iin_rms*sint
    # ---- inductor ripple: from a supplied ripple spec if given, else from L ----
    d_pk = max(1.0 - Vpk/Vo, 1e-3)
    di_peak_req = (float(curve(vac, *sp.di_pp_peak_curve)) if sp.di_pp_peak_curve else sp.di_pp_peak) or 0.0
    if sp.pct_ripple > 0 and Ipk_ch > 0:
        di_peak_req = sp.pct_ripple*Ipk_ch
    L_eff = (Vpk*d_pk/(di_peak_req*fsw)) if di_peak_req > 0 else sp.L   # back-out an effective L
    di = vin*d/(L_eff*fsw)
    dcm = i_ch < (di/2.0); ccm = ~dcm

    ms_fet = np.zeros_like(theta); ms_dio = np.zeros_like(theta)
    i_on = np.zeros_like(theta); i_off = np.zeros_like(theta)
    i_d_density = np.zeros_like(theta); i_d_repr = np.zeros_like(theta); rr_active = np.ones_like(theta)
    msc = i_ch**2 + di**2/12.0
    ms_fet[ccm] = msc[ccm]*d[ccm]; ms_dio[ccm] = msc[ccm]*(1.0-d[ccm])
    i_on[ccm] = np.maximum(i_ch[ccm]-di[ccm]/2.0, 0.0); i_off[ccm] = i_ch[ccm]+di[ccm]/2.0
    i_d_density[ccm] = i_ch[ccm]*(1.0-d[ccm]); i_d_repr[ccm] = i_ch[ccm]
    if np.any(dcm):
        v = vin[dcm]; ich = np.maximum(i_ch[dcm],1e-9); Tsw = 1.0/fsw
        ton = np.sqrt(ich*2.0*sp.L*Tsw*(Vo-v)/(v*Vo)); Ip = v*ton/sp.L; toff = Ip*sp.L/(Vo-v)
        d1 = np.clip(ton*fsw,0,1); d2 = np.clip(toff*fsw,0,1)
        ms_fet[dcm] = Ip**2*d1/3.0; ms_dio[dcm] = Ip**2*d2/3.0
        i_on[dcm] = 0.0; i_off[dcm] = Ip
        i_d_density[dcm] = 0.5*Ip*d2; i_d_repr[dcm] = (2.0/3.0)*Ip; rr_active[dcm] = 0.0

    eta_dummy, Tj_fet, Tj_dio, Tj_brT, Tj_brB = 0, 110.0, 110.0, 95.0, 95.0
    for _ in range(80):
        # Rds(on)(Id,Tj) evaluated at the local current at each line angle (not just the peak).
        i_rep = np.where(ms_fet > 0, np.sqrt(np.maximum(ms_fet, 1e-30)), 0.0)  # local on-state current
        rds_t = mos.rdson(Tj_fet, Id=i_rep)            # array if rdson_id_curve set, else scalar
        p_cond_fet_t = rds_t*ms_fet
        Esw = mos.e_switch(i_on, i_off, Vo, Tj_fet); p_sw_fet_t = fsw*Esw
        P_cond_fet = avg(p_cond_fet_t); P_sw_fet = avg(p_sw_fet_t)
        P_oss_fet = fsw*mos.eoss(Vo)          # (a) Eoss fully dissipated at hard turn-on (always full)
        P_gate = fsw*mos.qg*mos.k_qg*mos.vg_drive
        P_leak_fet = mos.p_leak(Vo, Tj_fet, avg(1.0-d))

        P_cond_dio = avg(dio.vf(i_d_repr, Tj_dio)*i_d_density + dio.rd*ms_dio)
        didt = mos.didt(i_off, Vo); Qrr = dio.qrr_eff(i_off, didt, Tj_dio)
        if dio.is_sic:
            # SiC Schottky: no minority-carrier reverse recovery. Its junction-capacitance charge
            # Qc is charged through the MOSFET channel at the MOSFET's hard turn-on, so that
            # 1/2*Vo*Qc energy is dissipated in the FET (not the diode). The diode keeps only its
            # forward-recovery energy e_fr.
            P_rr_to_fet = fsw*0.5*Vo*dio.qc*dio.k_qc
            P_sw_dio = fsw*dio.e_fr
        else:
            E_rec = Qrr*Vo
            P_rr_to_fet = fsw*avg(dio.rr_fet_frac*E_rec*rr_active)
            P_rr_to_dio = fsw*avg((1.0-dio.rr_fet_frac)*E_rec*rr_active)
            P_sw_dio = P_rr_to_dio + fsw*dio.e_fr
        P_leak_dio = (Vo*curve(Tj_dio,*dio.irev_curve)*avg(d)) if dio.irev_curve else 0.0

        P_fet_each = P_cond_fet+P_sw_fet+P_oss_fet+P_rr_to_fet+P_leak_fet
        P_dio_each = P_cond_dio+P_sw_dio+P_leak_dio
        P_fet_total = Nch*P_fet_each; P_dio_total = Nch*P_dio_each; P_gate_total = Nch*P_gate

        bl = br.loss(i_in, Tj_brT, Tj_brB, sp.fline, Vpk); P_bridge = bl["total"]

        # ---- thermal (per-device case nodes; optional separate bridge sink) ----
        Psemi_main = P_fet_total + P_dio_total
        if th.t_sink_fixed is not None: sink_main = th.t_sink_fixed
        elif th.separate_bridge_sink:  sink_main = th.t_ambient + Psemi_main*th.rth_sa
        else:                          sink_main = th.t_ambient + (Psemi_main+P_bridge)*th.rth_sa
        if th.separate_bridge_sink:
            sink_br = th.t_sink_bridge_fixed if th.t_sink_bridge_fixed is not None \
                      else th.t_ambient + P_bridge*th.rth_sa_bridge
        else:
            sink_br = sink_main
        Tj_fet_n = sink_main + P_fet_each*(mos.rth_jc+mos.rth_cs)
        Tj_dio_n = sink_main + P_dio_each*(dio.rth_jc+dio.rth_cs)
        Ptop_dev = bl["top"]/max(bl["ndev_top"],1); Pbot_dev = (bl["bottom"]/max(bl["ndev_bot"],1)) if bl["ndev_bot"] else 0.0
        Tj_brT_n = sink_br + Ptop_dev*(br.rth_jc+br.rth_cs)
        Tj_brB_n = sink_br + Pbot_dev*(br.rth_jc_bottom+br.rth_cs_bottom) if bl["ndev_bot"] else sink_br
        if (abs(Tj_fet_n-Tj_fet)<0.05 and abs(Tj_dio_n-Tj_dio)<0.05
                and abs(Tj_brT_n-Tj_brT)<0.05 and abs(Tj_brB_n-Tj_brB)<0.05):
            Tj_fet,Tj_dio,Tj_brT,Tj_brB = Tj_fet_n,Tj_dio_n,Tj_brT_n,Tj_brB_n; break
        Tj_fet,Tj_dio,Tj_brT,Tj_brB = Tj_fet_n,Tj_dio_n,Tj_brT_n,Tj_brB_n

    P_semi = P_fet_total + P_dio_total + P_bridge + P_gate_total
    P_system = Po*(1.0-eta)/eta
    Vo_ripple_pp = (Po/Vo)/(2*np.pi*(2*sp.fline)*sp.cout) if sp.cout > 0 else 0.0  # 2*fline bulk ripple
    out = {"Vac":vac, "eta_in_%":100*eta, "PF_in":pf, "DCM_%":100*float(np.mean(dcm)),
        "P_FET_total":P_fet_total, "P_FET_cond":Nch*P_cond_fet, "P_FET_sw":Nch*P_sw_fet,
        "P_FET_coss":Nch*P_oss_fet, "P_FET_rr":Nch*P_rr_to_fet, "P_FET_leak":Nch*P_leak_fet,
        "P_DIODE_total":P_dio_total, "P_D_cond":Nch*P_cond_dio, "P_D_sw":Nch*P_sw_dio,
        "P_BRIDGE_total":P_bridge, "P_BRIDGE_top":bl["top"], "P_BRIDGE_bottom":bl["bottom"],
        "P_gate_driver":P_gate_total,
        "P_SEMI_total":P_semi, "P_SYSTEM_total":P_system, "P_OTHER_implied":P_system-P_semi,
        "Tj_FET":Tj_fet, "Tj_DIODE":Tj_dio, "Tj_BRIDGE_top":Tj_brT, "Tj_BRIDGE_bottom":Tj_brB,
        "T_sink_main":sink_main, "T_sink_bridge":sink_br,
        "Po":Po, "Pin":Pin, "Iin_rms":Iin_rms, "Ipk_ch":Ipk_ch,
        "L_eff_uH":L_eff*1e6, "ripple_pk_%":100*float(np.max(di))/max(Ipk_ch,1e-9),
        "Vo_ripple_pp":Vo_ripple_pp}
    t_case_fet = sink_main + P_fet_each*mos.rth_cs; t_case_dio = sink_main + P_dio_each*dio.rth_cs
    pf_t = p_cond_fet_t + p_sw_fet_t + P_oss_fet + (P_rr_to_fet+P_leak_fet)
    pd_t = (dio.vf(i_d_repr,Tj_dio)*i_d_density + dio.rd*ms_dio) + P_sw_dio + P_leak_dio
    span_half = 1.0/(2.0*sp.fline)
    rf = transient_tj(pf_t, sp.fline, mos.zth_foster, t_case_fet, span=span_half)
    rdz = transient_tj(pd_t, sp.fline, dio.zth_foster, t_case_dio, span=span_half)
    if rf: out["Tj_FET_peak"],out["Tj_FET_ripple"] = rf[0],rf[2]
    if rdz: out["Tj_DIODE_peak"],out["Tj_DIODE_ripple"] = rdz[0],rdz[2]
    # --- bridge transient Tj (top diode and, if sync-bottom, bottom MOSFET) ---
    if br.zth_foster:
        bp_top, bp_bot = br.power_theta(i_in, Tj_brT, Tj_brB)
        if bl["top"] > 0 and bl["ndev_top"]:
            sc = Ptop_dev/max(float(np.mean(bp_top)), 1e-12)
            rbt = transient_tj(bp_top*sc, sp.fline, br.zth_foster, sink_br+Ptop_dev*br.rth_cs, span=span_half)
            if rbt: out["Tj_BRIDGE_top_peak"],out["Tj_BRIDGE_top_ripple"] = rbt[0],rbt[2]
        if bl["ndev_bot"] and bp_bot is not None and Pbot_dev > 0:
            sc = Pbot_dev/max(float(np.mean(bp_bot)), 1e-12)
            rbb = transient_tj(bp_bot*sc, sp.fline, br.zth_foster, sink_br+Pbot_dev*br.rth_cs_bottom, span=span_half)
            if rbb: out["Tj_BRIDGE_bottom_peak"],out["Tj_BRIDGE_bottom_ripple"] = rbb[0],rbb[2]
    if return_trace:
        # Converged intermediate quantities for ONE operating point, so a report can show the
        # step-by-step substitution with the engine's OWN numbers (not a re-derivation).
        ipk = int(np.argmax(i_ch))                                   # peak-of-line line angle
        rds_tj = float(mos.rdson(Tj_fet))                            # Rds(on) at Tj (nominal Id)
        i_fet_rms_ch = float(np.sqrt(max(avg(ms_fet), 0.0)))         # per-channel FET RMS current
        i_d_avg = avg(i_d_density)                                   # per-channel average diode current
        n_top = br.n_parallel_top if br.topology == "sync_bottom" else br.n_parallel
        out["trace"] = {
            "Vac": vac, "Vpk": Vpk, "Vo": Vo, "fsw": fsw, "Nch": Nch,
            "Iin_rms": Iin_rms, "Ipk_ch": Ipk_ch, "duty_pk": float(d[ipk]),
            "Tj_fet": Tj_fet, "Tj_dio": Tj_dio, "Tj_brT": Tj_brT, "Tj_brB": Tj_brB,
            "sink_main": sink_main, "Psemi_main": Psemi_main, "P_bridge": P_bridge,
            # ---- MOSFET ----
            "rds_25": mos.rdson_25, "rds_tj_factor": float(curve(Tj_fet, *mos._tjcoef())),
            "rds_tj": rds_tj, "i_fet_rms_ch": i_fet_rms_ch,
            "P_cond_fet_ch": P_cond_fet, "P_cond_fet_tot": Nch * P_cond_fet,
            "i_on_pk": float(i_on[ipk]), "i_off_pk": float(i_off[ipk]),
            "Esw_pk": float(Esw[ipk]), "Esw_avg": avg(Esw),
            "P_sw_fet_ch": P_sw_fet, "P_sw_fet_tot": Nch * P_sw_fet,
            "eoss_vo": float(mos.eoss(Vo)), "P_oss_ch": P_oss_fet, "P_oss_tot": Nch * P_oss_fet,
            "qg": mos.qg, "vg_drive": mos.vg_drive, "P_gate_ch": P_gate, "P_gate_tot": Nch * P_gate,
            "P_rr_fet_tot": Nch * P_rr_to_fet, "P_leak_fet_tot": Nch * P_leak_fet,
            "P_fet_each": P_fet_each, "rth_jc_fet": mos.rth_jc, "rth_cs_fet": mos.rth_cs,
            # ---- DIODE ----
            "is_sic": dio.is_sic, "vf_d_pk": float(dio.vf(i_d_repr[ipk], Tj_dio)),
            "i_d_avg": i_d_avg, "P_cond_dio_ch": P_cond_dio, "P_cond_dio_tot": Nch * P_cond_dio,
            "qc": dio.qc, "qrr_eff": float(Qrr) if not dio.is_sic else 0.0,
            "P_sw_dio_ch": P_sw_dio, "P_sw_dio_tot": Nch * P_sw_dio,
            "P_dio_each": P_dio_each, "rth_jc_dio": dio.rth_jc, "rth_cs_dio": dio.rth_cs,
            # ---- BRIDGE ----
            "topology": br.topology, "n_top": n_top,
            "vf_br_pk": float(br.vf(i_in[ipk] / max(n_top, 1), Tj_brT)),
            "P_bridge_top": bl["top"], "P_bridge_bottom": bl["bottom"],
            "rds_bot_tj": (br.rdson_bottom_25 * float(curve(Tj_brB, *br.rdson_bottom_tj)) / max(br.n_parallel_bottom, 1))
                          if br.topology == "sync_bottom" else 0.0,
            "rth_jc_br": br.rth_jc, "rth_cs_br": br.rth_cs,
        }
    if return_waveforms:
        # total instantaneous device powers (each averages back to its reported total loss)
        if br.topology == "sync_bottom":
            it = i_in/br.n_parallel_top
            rb = br.rdson_bottom_25*curve(Tj_brB,*br.rdson_bottom_tj)*br.k_rdson/br.n_parallel_bottom
            p_bridge_t = (br.vf(it,Tj_brT)*i_in + (br.rd/br.n_parallel_top)*i_in**2) + rb*i_in**2
        else:
            idev = i_in/br.n_parallel
            p_bridge_t = 2.0*(br.vf(idev,Tj_brT)*i_in + (br.rd/br.n_parallel)*i_in**2)
        out["waveforms"] = {
            "theta_deg": np.degrees(theta), "vin": vin, "duty": d,
            "i_ch": i_ch, "i_in": i_in, "i_on": i_on, "i_off": i_off,
            "di_pp": di, "dcm_mask": dcm,
            "p_fet_total_t": Nch*pf_t, "p_diode_total_t": Nch*pd_t,
            "p_bridge_total_t": p_bridge_t,
        }
    return out

def flatten_result(result):
    """Drop array payloads (e.g. 'waveforms') so a result row is safe for a DataFrame."""
    return {k: v for k, v in result.items()
            if not isinstance(v, (dict, list, tuple, np.ndarray))}

def simulate_vac_sweep(cfg, vac_list=None, return_waveforms=False):
    """Sweep the input-voltage list for a design dict and return a list of result dicts."""
    sp, mos, dio, br, th = design_from_dict(cfg)
    if vac_list is None:
        vac_list = cfg.get("run", {}).get("vac_list", [sp.vo/SQRT2*0.3])
    return [simulate_point(float(v), sp, mos, dio, br, th, return_waveforms=return_waveforms)
            for v in vac_list]

def show(t, r):
    print(f"\n=== {t} ===")
    print(f"  Vac={r['Vac']:.0f}V  eta(in)={r['eta_in_%']:.2f}%  PF={r['PF_in']:.3f}  DCM={r['DCM_%']:.1f}%")
    print(f"  MOSFET : {r['P_FET_total']:6.2f} W (cond {r['P_FET_cond']:.2f}, sw {r['P_FET_sw']:.2f}, "
          f"Coss {r['P_FET_coss']:.2f}, rr {r['P_FET_rr']:.2f}, leak {r['P_FET_leak']:.3f})")
    print(f"  Diode  : {r['P_DIODE_total']:6.2f} W (cond {r['P_D_cond']:.2f}, sw {r['P_D_sw']:.2f})")
    print(f"  Bridge : {r['P_BRIDGE_total']:6.2f} W (top {r['P_BRIDGE_top']:.2f}, bottom {r['P_BRIDGE_bottom']:.2f})")
    print(f"  SEMICONDUCTOR total : {r['P_SEMI_total']:6.2f} W   | system loss from eta: {r['P_SYSTEM_total']:.1f} W"
          f"  -> implied non-semi: {r['P_OTHER_implied']:.1f} W")
    print(f"  Tj: FET {r['Tj_FET']:.0f}C  Diode {r['Tj_DIODE']:.0f}C  Bridge_top {r['Tj_BRIDGE_top']:.0f}C "
          f"Bridge_bot {r['Tj_BRIDGE_bottom']:.0f}C  sink_main {r['T_sink_main']:.0f}C sink_br {r['T_sink_bridge']:.0f}C")
    if "Tj_FET_peak" in r:
        print(f"  transient: Tj_FET peak {r['Tj_FET_peak']:.1f}C (ripple {r['Tj_FET_ripple']:.1f}C)")


# ======================================================================================
#  DATA-DRIVEN DESIGN LAYER  (engine above is generic; all numbers come from the design)
# ======================================================================================
def design_from_dict(cfg):
    """Build (Spec, Mosfet, Diode, Bridge, Thermal) from a plain dict (inline or JSON-loaded).
    Curves may be tuples or lists, e.g. eta_curve=[[85,115,230,265],[0.94,0.96,0.98,0.984]]."""
    sp  = Spec(**cfg["spec"])
    mos = Mosfet(**cfg["mosfet"])
    dio = Diode(**cfg["diode"])
    br  = Bridge(**cfg["bridge"])
    th  = Thermal(**cfg["thermal"])
    return sp, mos, dio, br, th

def run_design(cfg, verbose=True):
    """Sweep the designer-provided input-voltage list and report semiconductor + thermal results."""
    sp, mos, dio, br, th = design_from_dict(cfg)
    run = cfg.get("run", {})
    vac_list = run.get("vac_list", [sp.vo / SQRT2 * 0.3])
    lim = run.get("tj_limit", {})
    rows = []
    if verbose:
        print(f"\n{'='*108}\nDESIGN: Nch={sp.nch}  Vo={sp.vo}V  fsw={sp.fsw/1e3:.0f}kHz  Tamb={th.t_ambient}C"
              f"  switch={mos.tech.upper()} {'(worst-case)' if mos.k_rdson!=1 else '(typical)'}\n{'='*108}")
        print(f"{'Vac':>4} {'Po':>6} {'eta%':>5} {'PF':>5} {'DCM%':>5} | {'FET':>6} {'Diode':>6} {'Bridge':>6}"
              f" {'semi':>6} | {'TjFET':>6} {'TjD':>5} {'TjBr':>5} | {'Vrip':>6}")
    for v in vac_list:
        r = simulate_point(float(v), sp, mos, dio, br, th); rows.append(r)
        if verbose:
            flag = ""
            for k, key in [("fet","Tj_FET"),("diode","Tj_DIODE"),("bridge","Tj_BRIDGE_top")]:
                if k in lim and r[key] > lim[k]: flag += f" !{k.upper()}>{lim[k]}C"
            print(f"{r['Vac']:>4.0f} {r['Po']:>6.0f} {r['eta_in_%']:>5.1f} {r['PF_in']:>5.3f} {r['DCM_%']:>5.1f}"
                  f" | {r['P_FET_total']:>6.2f} {r['P_DIODE_total']:>6.2f} {r['P_BRIDGE_total']:>6.2f}"
                  f" {r['P_SEMI_total']:>6.1f} | {r['Tj_FET']:>6.0f} {r['Tj_DIODE']:>5.0f} {r['Tj_BRIDGE_top']:>5.0f}"
                  f" | {r['Vo_ripple_pp']:>5.1f}V{flag}")
    return rows

# --------------------------------------------------------------------------------------
#  EXAMPLE DESIGN  --  THE DESIGNER EDITS THIS BLOCK (or supplies a JSON file).
#  Nothing in the engine above is hardcoded; every number below is a design input.
#  Output power, efficiency and PF are given as (Vac, value) curves so they can differ
#  across the universal input range (e.g. power fold-back at low line).
# --------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------
#  PARAMETER NOTES (read before filling a design)
#  - rdson_id_curve : normalized Rds(on) vs drain current, (Id, Rdson/Rdson_nominal). Captures
#                     quasi-saturation / package-lead / bondwire current dependence. Applied
#                     per-line-angle at the local on-state current. Leave None if not needed.
#  - esw_tco vs hot/cold curves : use esw_tco (fractional dEsw/dTj, e.g. 0.004 = 0.4%/C) when you
#                     have switching energy at ONE temperature; supply eon_curve_hot/eoff_curve_hot
#                     (at tj_hot_sw) instead when you have two-temperature datasheet curves -- then
#                     the tco is ignored and energy is interpolated linearly in Tj.
#  - vf_tco         : SIGNED forward-voltage slope in volts/C. Si pn diodes are typically NEGATIVE
#                     (~-2 mV/C); SiC Schottky is usually POSITIVE. Enter the sign explicitly.
#  - rr_fet_frac    : fraction of the diode recovery energy (Qrr*Vo) dissipated in the MOSFET;
#                     the remainder (1-frac) is dissipated in the diode. ~0.8-0.9 typical; tune to
#                     double-pulse/bench data. Ignored for SiC (Qc path).
#  - e_fr           : diode forward-recovery energy PER turn-on event [J]; multiplied by fsw here,
#                     so enter the per-event value (not a pre-averaged power).
# --------------------------------------------------------------------------------------
EXAMPLE_DESIGN = {
  "spec": {
    "vo": 400.0, "fsw": 100e3, "fline": 50.0, "nch": 2, "L": 300e-6, "cout": 680e-6,
    "po_curve":  [[90, 115, 180, 230, 265], [1200, 1600, 2000, 2000, 2000]],  # derated low line
    "eta_curve": [[90, 115, 180, 230, 265], [0.950, 0.962, 0.975, 0.982, 0.984]],
    "pf_curve":  [[90, 115, 180, 230, 265], [0.999, 0.998, 0.992, 0.985, 0.975]],
  },
  "mosfet": {  # paste your Si/SiC MOSFET datasheet numbers here
    "tech": "sic", "rdson_25": 0.060, "rdson_tj": [[25,125],[1.0,1.4]],
    "sw_method": "analytic", "ciss": 1500e-12, "qgd": 18e-9, "vth": 4.0, "vpl": 7.0,
    "gfs": 25.0, "vg": 18.0, "rg_on": 4.0, "rg_off": 2.0,
    "crss_curve": [[10,50,100,400],[900e-12,120e-12,45e-12,8e-12]],
    "k_turnoff": 0.8, "ls_loop": 5e-9, "esw_tco": 0.004,
    "eoss_at_v": [[100,400],[1.5e-6,6e-6]], "qg": 60e-9, "vg_drive": 18.0,
    "rth_jc": 0.6, "rth_cs": 0.3, "zth_foster": [[0.05,2e-4],[0.10,2e-3],[0.20,2e-2]],
  },
  "diode": {  # SiC Schottky boost diode
    "vf_curve": [[1,5,16],[1.05,1.35,1.7]], "vf_tco": 0.0015, "is_sic": True, "qc": 20e-9,
    "rth_jc": 0.7, "rth_cs": 0.3, "zth_foster": [[0.2,5e-4],[0.6,8e-3]],
  },
  "bridge": {  # plain diode bridge, 2 in parallel (set topology 'sync_bottom' for MOSFET bypass)
    "topology": "diode", "vf_curve": [[1,12,24],[0.75,0.95,1.15]], "vf_tco": -0.002,
    "n_parallel": 2, "rth_jc": 1.0, "rth_cs": 0.5,
  },
  "thermal": {"t_ambient": 45.0, "rth_sa": 0.35, "separate_bridge_sink": False},
  "run": {"vac_list": [90, 115, 180, 230, 265], "tj_limit": {"fet": 150, "diode": 150, "bridge": 130}},
}

if __name__ == "__main__":
    import sys, json
    if len(sys.argv) > 1:                       # python pfc_loss_model.py mydesign.json
        with open(sys.argv[1]) as f: cfg = json.load(f)
        print(f"Loaded design from {sys.argv[1]}")
    else:
        cfg = EXAMPLE_DESIGN
        print("No JSON given -- running built-in EXAMPLE_DESIGN (edit it or pass a JSON file).")
    run_design(cfg)
