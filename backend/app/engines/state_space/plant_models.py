import numpy as np
from typing import Dict, Any, Tuple
from app.engines.state_space.schemas import StateSpaceMatrices, OperatingPoint

def _boost_ccm_small_signal(op: OperatingPoint, inputs: Dict[str, Any], phases: int = 1) -> Tuple[StateSpaceMatrices, Dict[str, np.ndarray]]:
    L = inputs["L"] / phases; C = inputs.get("Cout", 2200e-6); R = op.r_load_ohm; D = op.duty
    # Inductor series resistance (DCR). A real inductor has DCR (~10-30 mΩ); omitting it (rL=0) makes
    # the CCM LC resonance almost undamped (Q~100+), which no reasonable voltage-loop compensator can
    # cross — the loop reads as unstable. Including it damps the resonance to a realistic Q so the
    # designed loop is stable, matching hardware.
    rL = float(inputs.get("r_L", 0.02)) / phases
    A = np.array([[-rL/L, -(1.0 - D)/L], [(1.0 - D)/C, -1.0/(R*C)]], dtype=float)
    B = np.array([[op.vout_v/L, 1.0/L], [-op.i_phase_avg_a/C, 0.0]], dtype=float)
    Cmat = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=float); Dmat = np.zeros((2,2), dtype=float)
    matrices = StateSpaceMatrices(A=A.tolist(), B=B.tolist(), C=Cmat.tolist(), D=Dmat.tolist(), states=["iL_eq","vC"], inputs=["duty_hat","vin_hat"], outputs=["iL_eq","vC"])
    return matrices, {"A": A, "B": B, "C": Cmat, "D": Dmat}

def topology_state_space_model(topology: str, op: OperatingPoint, inputs: Dict[str, Any]):
    if topology == "interleaved_boost_ccm":
        return _boost_ccm_small_signal(op, inputs, phases=2)
    return _boost_ccm_small_signal(op, inputs, phases=1)
