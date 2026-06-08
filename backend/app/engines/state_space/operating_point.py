import math
from typing import Dict, Any
from app.engines.state_space.schemas import OperatingPoint

def build_operating_point(topology: str, inputs: Dict[str, Any]) -> OperatingPoint:
    vac, vout, pout, eff, pf = inputs["Vac"], inputs["Vout"], inputs["Pout"], inputs["eff"], inputs["pf"]
    fsw, line_freq = inputs["fsw"], inputs.get("line_freq", 60.0)
    pin = pout / eff
    iin_rms = pin / (vac * pf)
    iin_pk = math.sqrt(2.0) * iin_rms
    vin = math.sqrt(2.0) * vac
    duty = max(0.0, min(1.0, 1.0 - vin / vout))
    r_load = (vout * vout) / max(pout, 1e-9)
    phases = 2 if topology == "interleaved_boost_ccm" else 1
    return OperatingPoint(topology=topology, vin_v=vin, vout_v=vout, pout_w=pout, fsw_hz=fsw, line_freq_hz=line_freq, duty=duty, iin_rms_a=iin_rms, iin_pk_a=iin_pk, i_phase_avg_a=iin_pk/phases, r_load_ohm=r_load)
