/**
 * frontend/src/types/DesignState.ts
 *
 * TypeScript mirror of backend/app/design_state.py
 * DOCUMENTATION ONLY — this file is not imported by App.tsx or client.ts.
 *
 * App.tsx stores state as: graphState: Record<string,unknown> | null
 * This interface documents what fields that dict actually contains.
 *
 * Schema version: 1.0
 * See: docs/DESIGN_STATE.md for field ownership rules.
 */

export interface IntakeApplication {
  vin_rms_min?:               number
  output_power_w_low_line?:   number
  output_power_w_high_line?:  number
  output_bus_voltage_v?:      number
  nominal_line_frequency_hz?: number
  [key: string]: unknown
}

export interface IntakeThermal {
  ambient_temp_c_max?: number
  hotspot_limit_c?:    number
  [key: string]: unknown
}

export interface IntakeControl {
  /** "Analog" | "Digital" | "Digital ARM" | "Recommend" */
  control_preference?: string
  [key: string]: unknown
}

export interface IntakeBusiness {
  /** e.g. ["Si"] | ["SiC"] | ["GaN"] */
  preferred_switch_technology?: string[]
  [key: string]: unknown
}

export interface IntakeCompliance {
  /** "Industrial" | "Medical" */
  application_class?:        string
  leakage_current_limit_ua?: number
  [key: string]: unknown
}

export interface Intake {
  application?: IntakeApplication
  thermal?:     IntakeThermal
  control?:     IntakeControl
  business?:    IntakeBusiness
  compliance?:  IntakeCompliance
  supply?:      Record<string, unknown>
  [key: string]: unknown
}

export interface TopologyRecommendation {
  recommended_topology?: string
  /** "ccm" | "crcm" | "dcm" */
  recommended_mode?: string
  [key: string]: unknown
}

export interface ControllerStrategy {
  /** "analog" | "digital" | "digital_arm" */
  recommended_controller_mode?: string
  reasoning?:                   string[]
  stated_control_preference?:   string
  [key: string]: unknown
}

export interface TopologySpecificInputs {
  switching_frequency_style?:       string
  recommended_frequency_hz?:        number | null
  recommended_frequency_range_hz?:  [number, number] | null
  ask_crest_ripple_ratio?:          boolean
  default_crest_ripple_ratio?:      number
  crest_ripple_ratio_guidance?:     string
  indicative_L_uH?:                 number
  indicative_Iin_pk_A?:             number
  // Confirmed after mini-intake submission
  confirmed_L_uH?:                  number
  confirmed_L_uH_sel?:              number
  confirmed_Iin_pk_A?:              number
  confirmed_dIL_A?:                 number
  dIL_pp_A?:                        number
  Iph_rms_A?:                       number
  [key: string]: unknown
}

/**
 * Canonical shape of the `state` dict passed to every backend endpoint.
 * Owner map — who sets each field:
 *   project_id, intake              → /mode-a/start
 *   topology_recommendation,
 *   selected_topology, selected_mode,
 *   controller_strategy             → /mode-a/approve-topology
 *   selected_controller_mode        → /mode-a/approve-controller
 *   selected_channels               → /mode-a/approve-channels
 *   topology_specific_inputs        → /mode-a/submit-mini-intake
 *   js_state                        → JS studio tools only
 */
export interface DesignState {
  project_id?:               string
  intake?:                   Intake
  topology_recommendation?:  TopologyRecommendation
  selected_topology?:        string
  selected_mode?:            string
  controller_strategy?:      ControllerStrategy
  selected_controller_mode?: string
  selected_channels?:        number
  topology_specific_inputs?: TopologySpecificInputs
  js_state?:                 Record<string, unknown>
  [key: string]: unknown
}
