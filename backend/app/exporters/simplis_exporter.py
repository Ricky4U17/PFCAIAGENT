from app.intake.compat import app_line_frequency_hz, compliance_leakage_limit_ma, compliance_leakage_limit_ua, app_efficiency_fraction
def generate_simplis_netlist(state):
    app = state["intake"]["application"]; approved = state.get("approved_tuning", {}); cur = approved.get("current_loop", {}); vol = approved.get("voltage_loop", {})
    return f'''* SIMPLIS netlist starter
* Topology: {state.get("selected_topology")}
* Vin={app["vin_rms_min"]} Vac, Vout={app["output_bus_voltage_v"]} V, Pout={app["output_power_w_nom"]} W
* Controller mode: {approved.get("controller_mode", state.get("controller_strategy", {}).get("selected_mode", "not_selected"))}
.param CUR_KP={cur.get("kp",1.0)}
.param CUR_KI={cur.get("ki",1.0)}
.param VOL_KP={vol.get("kp",1.0)}
.param VOL_KI={vol.get("ki",1.0)}
Vin in 0 SIN(0 {app["vin_rms_min"]*1.4142} {app["line_frequency_hz_nom"]})
L1 in sw 235u
Q1 sw gate 0 0 MOSFET_MODEL
D1 sw out DIODE_MODEL
Cout out 0 2200u
Rload out 0 42.25
'''