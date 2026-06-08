from __future__ import annotations
from typing import Any, Dict, List

def _rank_candidate(item: Dict[str, Any]) -> float:
    score = float(item.get("overall_score", 0.0))
    lifecycle = str(item.get("lifecycle", "Active")).lower()
    stock = str(item.get("stock_status", "unknown")).lower()

    if "nrnd" in lifecycle:
        score -= 3.0
    elif "obsolete" in lifecycle:
        score -= 6.0

    if "in stock" in stock:
        score += 2.0
    elif "limited" in stock:
        score += 0.5
    elif "out" in stock or "backorder" in stock:
        score -= 2.0

    lead_weeks = item.get("lead_time_weeks")
    try:
        if lead_weeks is not None:
            lw = float(lead_weeks)
            if lw <= 4:
                score += 1.0
            elif lw > 16:
                score -= 2.0
    except Exception:
        pass

    unit_price = item.get("unit_price_usd")
    try:
        if unit_price is not None:
            up = float(unit_price)
            if up <= 10:
                score += 0.5
            elif up >= 25:
                score -= 0.5
    except Exception:
        pass

    return round(score, 3)

def _normalize_semiconductor_candidates(vendor_candidates: Dict[str, Any]) -> List[Dict[str, Any]]:
    semis = vendor_candidates.get("semiconductors", {})
    cands = semis.get("candidates", []) if isinstance(semis, dict) else []
    normalized: List[Dict[str, Any]] = []

    for c in cands:
        normalized.append({
            "manufacturer": c.get("manufacturer", "Unknown"),
            "mpn": c.get("mpn", "Unknown"),
            "technology": c.get("technology", "Unknown"),
            "package": c.get("package"),
            "overall_score": c.get("overall_score", 0.0),
            "source_type": c.get("source_type", "scaffold"),
            "stock_status": "In Stock",
            "lead_time_weeks": 2,
            "unit_price_usd": 12.40 if c.get("technology") == "SiC" else 8.90,
            "lifecycle": "Active",
        })
    return normalized

def build_supply_chain_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    vendor_candidates = state.get("vendor_candidates", {})
    candidates = _normalize_semiconductor_candidates(vendor_candidates)

    if not candidates:
        return {
            "status": "incomplete",
            "blocking": False,
            "top_choices": [],
            "notes": ["No vendor candidates available yet. Run vendor scout before supply-chain advisory."],
        }

    ranked = []
    for c in candidates:
        item = dict(c)
        item["supply_chain_score"] = _rank_candidate(item)
        ranked.append(item)

    ranked.sort(key=lambda x: x["supply_chain_score"], reverse=True)
    top3 = ranked[:3]
    preferred = top3[0] if top3 else None

    risks = []
    for item in top3:
        if item.get("lead_time_weeks", 0) > 12:
            risks.append(f"{item['mpn']} has long lead time ({item['lead_time_weeks']} weeks).")
        if str(item.get("lifecycle", "")).lower() != "active":
            risks.append(f"{item['mpn']} lifecycle is {item['lifecycle']}.")

    return {
        "status": "advisory_ready",
        "blocking": False,
        "top_choices": top3,
        "recommended_choice": preferred,
        "risks": risks,
        "notes": [
            "Supply chain advisory is non-blocking in Phase 1.",
            "Pricing/stock in this starter implementation are scaffolded placeholders until real APIs are integrated.",
        ],
    }
