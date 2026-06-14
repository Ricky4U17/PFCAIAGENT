"""Standalone smoke test for sim_agent.adapter (Phase-2 pre-merge gate).
Run from backend/:  python -m app.sim_agent.smoke_adapter
Builds a package from a representative selected DesignResult + state, asserts the engine
validation returns ZERO errors, prints warnings, and runs compute() end-to-end."""
from app.magnetics.db import get_db
from app.sim_agent import adapter, pfc_inductor_engine as eng


def _pick_powder_key() -> str:
    db = get_db()
    for k, d in db._materials.items():
        if not k.startswith("pending:") and d.get("type") == "powder":
            return k
    raise RuntimeError("no powder material in DB")


def main():
    mat_key = _pick_powder_key()
    print("using material:", mat_key)

    # Representative selected candidate (EDGE-family 3-stack, N=47) — stand-in for a real
    # serialized DesignResult until Phase-1 wires a live candidate through.
    result = dict(
        part_number="0059071A2", N=47, stacks=3, core_type="powder", material_key=mat_key,
        T_core_C=100.0, Ve_total_cm3=29.2,
        OD_mm=40.9, ID_mm=21.3, HT_mm=17.89,
        Ae_single_mm2=153.0, Le_single_mm=94.0, Wa_single_mm2=355.0,
        AL_nom_nH=122.0, AL_tol_pct=8.0,
        n_strands=200, d_strand_mm=0.1, Cu_area_mm2=1.571, R_per_m_20C=0.01095,  # rho20/Cu_area (consistent)
        bundle_OD_computed_mm=2.23, Rac_Rdc=1.05,
        Rca_KperW=8.0, Rwa_KperW=6.0, Rcw_KperW=4.0,
        crowd_axial=1.46, H_Oe_worst=63.0,
    )
    state = dict(
        selected_channels=2,
        topology_specific_inputs=dict(recommended_frequency_hz=70000.0,
                                      confirmed_L_uH_sel=240.0,
                                      default_crest_ripple_ratio=0.095),
        intake=dict(
            application=dict(output_bus_voltage_v=393.0, vin_rms_min=90.0, vin_rms_max=264.0,
                             output_power_w_low_line=1700.0, output_power_w_high_line=3600.0),
            thermal=dict(ambient_temp_c_max=50.0, hotspot_limit_c=110.0),
        ),
    )

    pkg, vr = adapter.build_and_validate(result, state)
    print("\n--- package summary ---")
    print("steinmetz:", pkg["model"]["material"]["steinmetz"])
    print("retention:", pkg["model"]["material"]["retention"])
    print("Bsat:", pkg["model"]["material"]["Bsat"])
    print("geometry Ve_mm3 (single):", round(pkg["model"]["geometry"]["Ve_mm3"], 1))
    print("wire:", pkg["model"]["copper"]["wire"])
    print("operating points:", len(pkg["operating"]["points"]))
    print("fields present:", sorted((pkg.get("fields") or {}).keys()))

    print("\n--- validation ---")
    print("ok:", vr.ok, "| errors:", len(vr.errors))
    for e in vr.errors:   print("  ERROR  :", e)
    for w in vr.warnings: print("  WARNING:", w)
    assert vr.ok, "ADAPTER PRODUCED INVALID PACKAGE — fix the mapping, not the engine"

    res = eng.compute(pkg)
    print("\n--- compute ---")
    print("verdict:", res["verdict"])
    print("tiers:", res["tier"])
    w = res["worst"]
    print(f"Lguar={w['Lmin_guarantee_uH']:.0f} uH  worstLoss={w['loss']['Ptot_max']:.2f} W  "
          f"Bmax={w['Bmax']['Bmax']:.3f} T  dT={w['dT']['dT']:.1f} C")
    print("\nSMOKE OK")


if __name__ == "__main__":
    main()
