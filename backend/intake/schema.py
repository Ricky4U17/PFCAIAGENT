from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class ApplicationRequirements(BaseModel):
    vin_rms_min: float = 90.0
    vin_rms_max: float = 264.0
    # MA-5 fix: float not Literal — supports 50, 60, and 400 Hz (aviation/defence).
    nominal_line_frequency_hz: float = 60.0
    input_frequency_range_hz_min: float = 47.0
    input_frequency_range_hz_max: float = 63.0
    output_bus_voltage_v: float = 390.0
    dc_bus_voltage_ripple_pk_pk_v: float = 20.0
    output_power_w_nom: float = 3600.0
    output_power_w_low_line: float = 1700.0
    output_power_w_high_line: float = 3600.0
    power_factor_target: float = 0.99
    efficiency_target_percent: float = 98.0
    hold_up_time_ms: float = 20.0


class ThermalRequirements(BaseModel):
    cooling_type: Literal["fan_cooled", "natural_convection", "liquid_cooled", "conduction_cooled"] = "fan_cooled"
    ambient_temp_c_max: float = 50.0
    max_temp_rise_c: float = 45.0
    hotspot_limit_c: float = 110.0
    max_enclosure_rth_c_per_w: float = 0.5


class MechanicalRequirements(BaseModel):
    height_limit_mm: Optional[float] = None
    power_density_priority: int = 8


class ComplianceRequirements(BaseModel):
    conducted_emi_class: Literal["FCC Class B", "FCC Class A"] = "FCC Class B"
    radiated_emi_class: Literal["FCC Class B", "FCC Class A"] = "FCC Class B"
    harmonics_class: Literal["EN61000-3-12", "EN61000-3-2"] = "EN61000-3-2"
    surge_requirement: str = "1 KV Line to Line / 2KV Line to Ground Class A"
    # MA-5 fix: leakage stored in µA (1 mA = 1000 µA) — compat.py bridges old mA fields.
    leakage_current_limit_ua: float = 3500.0
    application_class: Literal["Industrial", "IT Equipment", "Medical", "Telecom", "EV Charge"] = "Industrial"
    esd_requirement: Optional[str] = None
    radiated_field_requirement: Optional[str] = None
    conducted_immunity_requirement: Optional[str] = None
    eft_burst_requirement: str = "EN61000-4-4 Level 3 Criteria A"
    magnetic_field_requirement: str = "EN61000-4-8 Level 4 Test Criteria A"
    voltage_dips_requirement: str = "EN61000-4-11 Class 3 Criteria A"
    semi_f47_required: bool = False


class ControlPreferences(BaseModel):
    control_preference: Literal["Analog", "Digital", "Digital ARM", "Recommend"] = "Recommend"


class BusinessPreferences(BaseModel):
    cost_priority: int = 7
    efficiency_priority: int = 9
    power_density_priority: int = 8
    implementation_risk_priority: int = 8
    preferred_switch_technology: List[str] = Field(default_factory=lambda: ["Si", "SiC", "GaN"])


class SupplyPreferences(BaseModel):
    preferred_vendors: List[str] = Field(default_factory=list)
    avoid_vendors: List[str] = Field(default_factory=list)


class FullIntake(BaseModel):
    application: ApplicationRequirements = ApplicationRequirements()
    thermal: ThermalRequirements = ThermalRequirements()
    mechanical: MechanicalRequirements = MechanicalRequirements()
    compliance: ComplianceRequirements = ComplianceRequirements()
    control: ControlPreferences = ControlPreferences()
    business: BusinessPreferences = BusinessPreferences()
    supply: SupplyPreferences = SupplyPreferences()
