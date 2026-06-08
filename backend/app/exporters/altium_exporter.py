def generate_altium_design_stub(state):
    return {"topology": state.get("selected_topology"), "components": [{"ref":"L1","type":"Inductor","value":"235uH"},{"ref":"Q1","type":"MOSFET","value":"TBD"},{"ref":"Cout","type":"Capacitor","value":"2200uF"}], "nets": [["Vin","L1"],["L1","Q1"],["Q1","Cout"],["Cout","GND"]]}
