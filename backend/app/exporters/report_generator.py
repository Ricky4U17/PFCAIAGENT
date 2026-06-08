"""report_generator.py — I-6: serialises structured sections at export time only."""
from __future__ import annotations
import os
from app.services.report_helpers import (
    build_topology_section, build_advisory_section,
    build_approved_tuning_section, section_to_markdown, compile_report,
)
from app.exporters.pdf_report_generator import generate_pdf_report

MODE_B_ORDER = [
    "input_processing","duty_and_ripple","inductor_sizing","worst_case_angle",
    "waveform_reconstruction","magnetic_design","magnetic_design_v2_advisory",
    "magnetic_fea_advisory","protection_compliance","emi_filter",
    "layout_parasitics_advisory","control_loops","state_space_analysis",
    "guardrail_v2_advisory","bidirectional_thermal","cad_thermal_integration_advisory",
    "vendor_scout","supply_chain_advisory","reliability_mtbf_advisory","design_graphs",
    "simulation_export","closed_loop_simulation_advisory","firmware_generation_advisory",
    "pcb_floorplanning_advisory","altium_export",
]

ADVISORY_MAP = [
    ("Guardrail v2 Advisory",                  "guardrail_v2_results"),
    ("Supply Chain Advisory",                  "supply_chain_results"),
    ("Magnetic Design v2 Advisory",            "magnetic_design_v2_results"),
    ("Closed-loop Simulation Verification",    "simulation_verification_results"),
    ("Layout Parasitics Advisory",             "layout_parasitics_results"),
    ("Firmware Generation Advisory",           "firmware_generation_results"),
    ("Reliability / MTBF Advisory",            "reliability_mtbf_results"),
    ("PCB Floorplanning Advisory",             "pcb_floorplanning_results"),
    ("CAD Thermal Integration Advisory",       "cad_thermal_integration_results"),
    ("Magnetic FEA Advisory",                  "magnetic_fea_results"),
]


def generate_final_report_markdown(state: dict) -> str:
    md_sections = [
        "# Final PFC Design Report",
        (f"## Project Summary\n"
         f"- **Project ID:** {state.get('project_id')}\n"
         f"- **Selected topology:** {state.get('selected_topology')}\n"
         f"- **Schema version:** {state.get('schema_version','n/a')}\n"
         f"- **Errors during run:** {len(state.get('errors',[]))}"),
    ]
    errors = state.get("errors", [])
    if errors:
        md_sections.append("## Run Errors\n" + "\n".join(f"- {e}" for e in errors))
    if state.get("topology_recommendation"):
        raw = state["report_sections"].get("topology_selection") \
              or build_topology_section(state["topology_recommendation"])
        md_sections.append(section_to_markdown(raw))
    for name in MODE_B_ORDER:
        raw = state.get("report_sections", {}).get(name)
        if raw is not None:
            md_sections.append(section_to_markdown(raw))
    for title, key in ADVISORY_MAP:
        result = state.get(key)
        if result:
            md_sections.append(section_to_markdown(build_advisory_section(title, result)))
    if state.get("approved_tuning"):
        md_sections.append(section_to_markdown(build_approved_tuning_section(state["approved_tuning"])))
    return compile_report(md_sections)


def generate_final_report_bundle(state: dict, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    md  = generate_final_report_markdown(state)
    pid = state.get("project_id", "project")
    md_path  = os.path.join(output_dir, f"{pid}_final_report.md")
    pdf_path = os.path.join(output_dir, f"{pid}_final_report.pdf")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    generate_pdf_report(state, md, pdf_path)
    return {"markdown_path": md_path, "pdf_path": pdf_path}
