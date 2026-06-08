from app.vendors.semiconductors.semiconductor_selector import select_semiconductors_from_state

def scout_vendors(state):
    semiconductors = select_semiconductors_from_state(state, role="pfc_switch")
    return {"semiconductors": semiconductors, "magnetics": {"notes": ["Magnetics selector scaffold remains to be extended."]}}
