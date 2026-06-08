from app.vendors.semiconductors.infineon_client import InfineonClient
from app.vendors.semiconductors.st_client import STClient

def select_semiconductors_from_state(state, role="pfc_switch"):
    inp = state.get("step_results", {}).get("input_processing", {})
    app = state["intake"]["application"]; thermal = state["intake"]["thermal"]; business = state["intake"]["business"]
    req = {"role": role, "topology": state.get("selected_topology", "interleaved_boost_ccm"), "vds_required_v": app["output_bus_voltage_v"] * 1.2, "current_rms_required_a": inp.get("Irms", 10.0)/2, "current_peak_required_a": inp.get("Ipk", 15.0)/2, "fsw_hz": state.get("human_feedback", {}).get("overrides", {}).get("fsw", 70000.0), "cooling_type": thermal["cooling_type"], "preferred_technologies": business.get("preferred_switch_technology", ["Si","SiC","GaN"])}
    cands = InfineonClient().search_mosfets(req) + STClient().search_mosfets(req)
    ranked = []
    for c in cands:
        score = 8.0
        if c.vds_v and c.vds_v < req["vds_required_v"]: score -= 5.0
        if c.technology == "SiC": score += 0.5
        ranked.append({"manufacturer": c.manufacturer, "mpn": c.mpn, "technology": c.technology, "vds_v": c.vds_v, "rds_on_ohm": c.rds_on_ohm, "qg_nc": c.qg_nc, "package": c.package, "overall_score": round(score,2), "source_type": c.source_type})
    ranked.sort(key=lambda x: x["overall_score"], reverse=True)
    return {"requirements_summary": req, "candidates": ranked, "recommended_part": ranked[0] if ranked else None, "runner_up_part": ranked[1] if len(ranked) > 1 else None, "reasoning": ["Starter manufacturer-prioritized selector."]}
