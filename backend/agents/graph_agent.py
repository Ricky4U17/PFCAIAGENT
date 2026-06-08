import os
from app.graphs.design_graphs import plot_topology_scores, plot_duty_vs_line_angle
from app.intake.compat import app_line_frequency_hz, compliance_leakage_limit_ma, compliance_leakage_limit_ua, app_efficiency_fraction

def generate_design_graphs(state):
    project_id = state.get("project_id", "project")
    out = os.path.join("generated_artifacts", project_id, "graphs")
    os.makedirs(out, exist_ok=True)
    artifacts = {}
    topo = state.get("topology_recommendation", {})
    if topo.get("ranking"):
        artifacts["topology_scores"] = plot_topology_scores(topo["ranking"], out)
    app = state["intake"]["application"]
    artifacts["duty_vs_line_angle"] = plot_duty_vs_line_angle(app.get("vin_rms_min", 90.0), app.get("output_bus_voltage_v", 390.0), out, app_line_frequency_hz(app))
    return artifacts