"""
app/mode_b/registry.py
Single source of truth for all 25 Mode B engineering steps.

RULES (read before touching this file):
  1. Never remove a step entry — only change its status.
  2. Add new steps by incrementing the key; never reuse numbers.
  3. Update 'status' from QUEUED → IN_PROGRESS → DONE.
  4. 'outputs' lists every artifact the step produces.
  5. 'implemented_in' lists every file that was edited to implement the step.
  6. Run `python -m pytest tests/test_regression.py` before any commit.
"""
from __future__ import annotations
from typing import Literal

Status = Literal["DONE", "IN_PROGRESS", "QUEUED"]

# ── Step schema ────────────────────────────────────────────────────────────
# key       : unique snake_case identifier (must match LangGraph node name)
# number    : 1-25 (never reuse)
# status    : DONE | IN_PROGRESS | QUEUED
# outputs   : list of artifact types this step produces
# api_route : FastAPI endpoint path (None if not exposed yet)
# pdf_pages : range of pages in Steps 1-12 PDF (None if not in PDF)
# implemented_in: files edited to implement (relative to backend/)
# next_inputs   : parameters passed to the NEXT step
# description   : one-sentence summary

REGISTRY: dict[int, dict] = {

    # ── Mode B Steps 1-12: covered by the PDF report engine ───────────────

    1: dict(
        key              = "input_processing",
        status           = "DONE",
        outputs          = ["pdf_section"],
        api_route        = "/mode-b/generate-report",
        pdf_pages        = (3, 4),
        implemented_in   = ["app/mode_b/generate_report.py",
                            "app/mode_b/calculations.py"],
        next_inputs      = ["OPS", "Vout", "fsw", "r_input", "N_phases"],
        description      = "Extracts confirmed Mode A parameters; builds 9-point OPS array.",
    ),

    2: dict(
        key              = "duty_and_ripple",
        status           = "DONE",
        outputs          = ["pdf_section", "table:step2_results"],
        api_route        = "/mode-b/generate-report",
        pdf_pages        = (4, 6),
        implemented_in   = ["app/mode_b/generate_report.py",
                            "app/mode_b/calculations.py:step2_input_params"],
        next_inputs      = ["Vin_pk[]", "Dpk[]", "Iin_pk[]", "KDpk[]"],
        description      = "Calculates Vin_pk, D_pk, Iin_rms, Iin_pk, K(D) for all 9 op-points.",
    ),

    3: dict(
        key              = "inductor_sizing",
        status           = "DONE",
        outputs          = ["pdf_section", "value:L_calc_uH", "value:L_selected_uH"],
        api_route        = "/mode-b/generate-report",
        pdf_pages        = (7, 8),
        implemented_in   = ["app/mode_b/generate_report.py",
                            "app/mode_b/calculations.py:step4_inductance"],
        next_inputs      = ["L_phi"],
        description      = "Sizes L_phi at 90 Vac low-line: L = Vin_pk×D/(K(D)×r×Iin_pk×fsw). L same for all N.",
    ),

    4: dict(
        key              = "worst_case_angle",
        status           = "DONE",
        outputs          = ["pdf_section", "table:worst_case_results"],
        api_route        = "/mode-b/generate-report",
        pdf_pages        = (13, 16),
        implemented_in   = ["app/mode_b/generate_report.py",
                            "app/mode_b/calculations.py:step7_8_worst_case"],
        next_inputs      = ["dIL_max", "theta1[]", "theta2[]"],
        description      = "Finds worst-case line angle for maximum per-phase ripple across all op-points.",
    ),

    5: dict(
        key              = "waveform_reconstruction",
        status           = "DONE",
        outputs          = ["pdf_section", "plot:phase_A_B_waveforms",
                            "plot:input_ripple", "plot:duty_cycle_waveforms",
                            "table:compact_ripple"],
        api_route        = "/mode-b/generate-report",
        pdf_pages        = (17, 30),
        implemented_in   = ["app/mode_b/generate_report.py",
                            "app/mode_b/calculations.py:gen_waveforms"],
        next_inputs      = ["IL_rms[]", "Ipk_ph"],
        description      = "Generates per-phase and total input current waveforms; Steps 10-12 plots.",
    ),

    6: dict(
        key              = "magnetic_design",
        status           = "DONE",
        outputs          = ["api_json:core_selection", "value:N_turns",
                            "value:air_gap_mm", "value:litz_wire_spec",
                            "value:P_total_W", "value:dT_rise_C"],
        api_route        = "/mode-b/step6-magnetic-design",
        pdf_pages        = None,   # not yet in PDF — add when Step 6 PDF section built
        implemented_in   = ["app/mode_b/magnetic_design.py",
                            "app/main.py:step6"],
        next_inputs      = ["N_turns", "L_selected_uH", "Bpk", "wire_spec"],
        description      = "Selects core (ETD49/59/E65/KoolMu), sizes turns, gap, Litz wire; checks Ku, ΔT.",
    ),

    # ── Steps 7-25: QUEUED — implement by following DEVELOPMENT_GUIDE.md ─

    7: dict(
        key              = "magnetic_design_v2_advisory",
        status           = "DONE",
        outputs          = ["api_json:top5_candidates", "api_json:step13_full",
                            "table:L_vs_Vin", "table:loss_25C", "table:loss_100C"],
        api_route        = "/mode-b/step7/run-sizing",
        pdf_pages        = None,
        implemented_in   = [
            "app/mode_b/step7_magnetic_calc.py",
            "app/mode_b/step8_time_domain.py",
            "app/magnetics/db.py",
            "app/magnetics/schema.py",
            "app/magnetics/extractor.py",
            "app/main.py:step7_run_sizing",
        ],
        next_inputs      = ["approved_design", "material_key", "N", "Ae_total_mm2"],
        description      = ("Full magnetic design: 4-gate HITL (material→supplier→grade→core), "
                            "iterative sizing engine, Top 5 candidates with composite scoring. "
                            "Matches reference Step 13 exactly. MagneticsDB agent owns all data."),
    ),

    8: dict(
        key              = "magnetic_fea_advisory",
        status           = "DONE",
        outputs          = ["api_json:pcore_time_domain", "table:pcore_avg_all_vac",
                            "plot:Bac_pk_overlay", "plot:Pcore_overlay",
                            "value:power_law_n", "value:power_law_k"],
        api_route        = "/mode-b/step8/time-domain",
        pdf_pages        = None,
        implemented_in   = [
            "app/mode_b/step8_time_domain.py",
            "app/main.py:step8_time_domain",
        ],
        next_inputs      = ["Pcore_avg[]", "power_law_n", "power_law_k"],
        description      = ("Time-domain core-loss modeling (reference Step 14). "
                            "Computes Bac_pk(t) and Pcore(t) across half line cycle. "
                            "Fits Pcore=k×B^n, integrates for accurate Pcore_avg. "
                            "Key: crest-point overestimates 90Vac by 83%, underestimates 230Vac by 126%."),
    ),

    9: dict(
        key              = "protection_compliance",
        status           = "QUEUED",
        outputs          = ["protection_spec"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "OVP (Vout>415V), OCP (IL>Ipk×1.2), OTP (Tj>100°C), SCP latch-off, IEC 60601-1 leakage shutdown.",
    ),

    10: dict(
        key              = "emi_filter",
        status           = "QUEUED",
        outputs          = ["emi_filter_spec", "component_values"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "DM/CM filter sizing from ΔIL; Y-cap constrained by 500 µA leakage (Medical); insertion loss target.",
    ),

    11: dict(
        key              = "layout_parasitics_advisory",
        status           = "QUEUED",
        outputs          = ["layout_guidelines"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "PCB parasitics: trace inductance budget, copper weight, thermal vias, gate loop area.",
    ),

    12: dict(
        key              = "control_loops",
        status           = "QUEUED",
        outputs          = ["compensator_design", "bode_plots"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Voltage loop and current loop compensation; phase margin ≥45°; UCC28070A / C2000 specific.",
    ),

    13: dict(
        key              = "state_space_analysis",
        status           = "QUEUED",
        outputs          = ["averaged_model", "eigenvalues"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Averaged state-space model for CCM boost PFC; Gvd, Gid transfer functions.",
    ),

    14: dict(
        key              = "guardrail_v2_advisory",
        status           = "QUEUED",
        outputs          = ["design_rule_check_report"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Automated design rule check: power budget, derating, thermal margin, safety margins.",
    ),

    15: dict(
        key              = "bidirectional_thermal",
        status           = "QUEUED",
        outputs          = ["thermal_model", "junction_temps"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Full thermal network: junction → case → heatsink → ambient. Loops back to inductor sizing if Tj > limit.",
    ),

    16: dict(
        key              = "cad_thermal_integration_advisory",
        status           = "QUEUED",
        outputs          = ["cad_export_spec"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "STEP/IGES thermal model export advisory; Ansys Icepak / FloTHERM setup parameters.",
    ),

    17: dict(
        key              = "vendor_scout",
        status           = "QUEUED",
        outputs          = ["bom_candidates"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Component vendor selection: SiC MOSFETs, core material, Litz wire, capacitors, gate drivers.",
    ),

    18: dict(
        key              = "supply_chain_advisory",
        status           = "QUEUED",
        outputs          = ["supply_chain_report"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Lead time, lifecycle, multi-source, approved vendors list for Medical.",
    ),

    19: dict(
        key              = "reliability_mtbf_advisory",
        status           = "QUEUED",
        outputs          = ["mtbf_estimate"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "MIL-HDBK-217F / Telcordia parts count reliability; MTBF estimate at 40°C ambient.",
    ),

    20: dict(
        key              = "design_graphs",
        status           = "QUEUED",
        outputs          = ["design_summary_pdf"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Final design summary: all waveforms, efficiency map, derating curves, BOM cost breakdown.",
    ),

    21: dict(
        key              = "simulation_export",
        status           = "QUEUED",
        outputs          = ["ltspice_netlist", "psim_model"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Export LTspice / PSIM netlist with all computed component values.",
    ),

    22: dict(
        key              = "closed_loop_simulation_advisory",
        status           = "QUEUED",
        outputs          = ["simulation_setup"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Closed-loop PFC simulation checklist: startup, transient load step, line step, PF measurement.",
    ),

    23: dict(
        key              = "firmware_generation_advisory",
        status           = "QUEUED",
        outputs          = ["firmware_spec"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "TI C2000 / STM32G4 firmware outline: PFC ISR, ADC sampling, leakage monitor, EEPROM fault log.",
    ),

    24: dict(
        key              = "pcb_floorplanning_advisory",
        status           = "QUEUED",
        outputs          = ["floorplan_guidelines"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "PCB placement rules: power loop, control isolation, heatsink keepout, creepage for Medical.",
    ),

    25: dict(
        key              = "altium_export",
        status           = "QUEUED",
        outputs          = ["altium_schematic_template", "library_parts"],
        api_route        = None,
        pdf_pages        = None,
        implemented_in   = [],
        next_inputs      = [],
        description      = "Altium Designer schematic template with all component values pre-populated.",
    ),
}


def get_step(number: int) -> dict:
    """Return step metadata. Raises KeyError if number not in 1-25."""
    if number not in REGISTRY:
        raise KeyError(f"Step {number} not in registry. Valid range: 1-25.")
    return REGISTRY[number]


def steps_by_status(status: Status) -> list[tuple[int, dict]]:
    """Return list of (number, step_dict) for all steps with given status."""
    return [(n, s) for n, s in REGISTRY.items() if s["status"] == status]


def implemented_steps() -> list[int]:
    return [n for n, s in REGISTRY.items() if s["status"] == "DONE"]


def next_step_to_implement() -> tuple[int, dict] | None:
    queued = steps_by_status("QUEUED")
    return queued[0] if queued else None


def print_status() -> None:
    done    = steps_by_status("DONE")
    prog    = steps_by_status("IN_PROGRESS")
    queued  = steps_by_status("QUEUED")
    print(f"Mode B steps: {len(done)} DONE · {len(prog)} IN_PROGRESS · {len(queued)} QUEUED")
    for n, s in REGISTRY.items():
        sym = {"DONE":"✓","IN_PROGRESS":"→","QUEUED":"·"}[s["status"]]
        print(f"  {sym} Step {n:2d}: {s['key']:<45} [{s['status']}]")


if __name__ == "__main__":
    print_status()
    nxt = next_step_to_implement()
    if nxt:
        print(f"\nNext to implement: Step {nxt[0]} — {nxt[1]['key']}")
        print(f"  Description: {nxt[1]['description']}")
