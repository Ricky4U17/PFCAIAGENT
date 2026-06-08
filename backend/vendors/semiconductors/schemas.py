from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal

TechnologyType = Literal["Si","SiC","GaN","Unknown"]
DeviceCategory = Literal["MOSFET","Diode","Rectifier","Unknown"]

class SemiconductorRequirement(BaseModel):
    role: str = "pfc_switch"
    category: DeviceCategory = "MOSFET"
    topology: str = "interleaved_boost_ccm"
    preferred_technologies: List[TechnologyType] = Field(default_factory=lambda: ["Si","SiC","GaN"])
    vds_required_v: float
    current_rms_required_a: float
    current_peak_required_a: float
    fsw_hz: float
    cooling_type: str = "fan_cooled"

class RawSemiconductorCandidate(BaseModel):
    manufacturer: str
    mpn: str
    category: DeviceCategory = "MOSFET"
    technology: TechnologyType = "Unknown"
    vds_v: Optional[float] = None
    current_cont_a: Optional[float] = None
    rds_on_ohm: Optional[float] = None
    qg_nc: Optional[float] = None
    tr_ns: Optional[float] = None
    tf_ns: Optional[float] = None
    vf_v: Optional[float] = None
    package: Optional[str] = None
    lifecycle: Optional[str] = None
    source_url: Optional[str] = None
    source_type: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
