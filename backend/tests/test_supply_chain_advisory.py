from app.agents.supply_chain_agent import node_supply_chain_advisory

def test_supply_chain_advisory_returns_structured_result():
    state = {
        "vendor_candidates": {
            "semiconductors": {
                "candidates": [
                    {
                        "manufacturer": "Infineon",
                        "mpn": "IMW65R072M1H",
                        "technology": "SiC",
                        "package": "TO-247",
                        "overall_score": 9.2,
                        "source_type": "manufacturer",
                    },
                    {
                        "manufacturer": "ST",
                        "mpn": "SCT040H65G3AG",
                        "technology": "SiC",
                        "package": "HiP247",
                        "overall_score": 8.9,
                        "source_type": "manufacturer",
                    },
                ]
            }
        }
    }
    out = node_supply_chain_advisory(state)
    result = out["supply_chain_results"]
    assert result["status"] == "advisory_ready"
    assert result["blocking"] is False
    assert len(result["details"]["top_choices"]) >= 1
    assert result["details"]["recommended_choice"] is not None

def test_supply_chain_advisory_handles_missing_candidates():
    out = node_supply_chain_advisory({})
    result = out["supply_chain_results"]
    assert result["status"] == "incomplete"
    assert result["blocking"] is False
