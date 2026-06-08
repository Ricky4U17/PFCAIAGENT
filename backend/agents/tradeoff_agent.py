from __future__ import annotations
from typing import Dict, Any, List
from app.llm.client import LLMClient
from app.llm.prompts import TRADEOFF_SYSTEM_PROMPT
from app.llm.schemas import TradeoffResponse

def build_tradeoff_summary(context: Dict[str, Any], options: List[Dict[str, Any]], citations: List[Dict[str, Any]]) -> TradeoffResponse:
    llm = LLMClient()
    try:
        return llm.generate_structured(TRADEOFF_SYSTEM_PROMPT, {"context": context, "options": options}, TradeoffResponse)
    except Exception:
        return TradeoffResponse(
            headline=f"Tradeoff summary for {context.get('current_step','step')}",
            pros=["Useful visibility into the design choice."],
            cons=["Still a starter heuristic."],
            recommendation="Review before approving.",
            next_question="Would you like to continue or adjust inputs?",
            citations=[],
        )
