from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

CompensatorType = Literal["Type1", "Type2", "Type3", "PI"]

class OperatingPoint(BaseModel):
    topology: str
    vin_v: float
    vout_v: float
    pout_w: float
    fsw_hz: float
    line_freq_hz: float
    duty: float
    iin_rms_a: float
    iin_pk_a: float
    i_phase_avg_a: float
    r_load_ohm: float

class StateSpaceMatrices(BaseModel):
    A: List[List[float]]
    B: List[List[float]]
    C: List[List[float]]
    D: List[List[float]]
    states: List[str]
    inputs: List[str]
    outputs: List[str]

class LoopTuningSuggestion(BaseModel):
    loop_name: str
    compensator_type: CompensatorType
    kp: float
    ki: float
    kz_hz: Optional[float] = None
    kpole_hz: Optional[float] = None
    target_fc_hz: float
    achieved_fc_hz: float
    phase_margin_deg: float
    gain_margin_db: float
    notes: List[str] = Field(default_factory=list)

class BodeData(BaseModel):
    frequency_hz: List[float]
    plant_mag_db: List[float]
    plant_phase_deg: List[float]
    loop_mag_db: List[float]
    loop_phase_deg: List[float]
    closed_mag_db: List[float]
    closed_phase_deg: List[float]

class StepResponseData(BaseModel):
    time_s: List[float]
    response: List[float]
    reference: List[float]
    overshoot_percent: float
    settling_time_s: float
    rise_time_s: float

class LoopAnalysisResult(BaseModel):
    plant_tf_num: List[float]
    plant_tf_den: List[float]
    compensator_tf_num: List[float]
    compensator_tf_den: List[float]
    suggestion: LoopTuningSuggestion
    bode: BodeData
    step: StepResponseData

class StateSpaceAnalysisResult(BaseModel):
    operating_point: OperatingPoint
    matrices: StateSpaceMatrices
    current_loop: LoopAnalysisResult
    voltage_loop: LoopAnalysisResult
    frontend_payload: Dict[str, Any]
    notes: List[str] = Field(default_factory=list)
