from __future__ import annotations
from typing import Dict, Any, List
from app.llm.client import LLMClient
from app.llm.prompts import EDUCATOR_SYSTEM_PROMPT
from app.llm.schemas import EducatorResponse

def build_educator_response(step_name: str, results: Dict[str, Any], verification: Dict[str, Any], tradeoffs: Dict[str, Any], citations: List[Dict[str, Any]]) -> EducatorResponse:
    llm = LLMClient()
    try:
        return llm.generate_structured(EDUCATOR_SYSTEM_PROMPT, {"step_name": step_name, "results": results}, EducatorResponse)
    except Exception:
        return EducatorResponse(
            summary=f"{step_name.replace('_',' ').title()} completed.",
            key_points=["Result generated.", "Review key metrics before proceeding."],
            choices=["Approve", "Modify", "Repeat"],
            cautions=verification.get("notes", []),
            citations=[],
        )
