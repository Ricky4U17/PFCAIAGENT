from pydantic import BaseModel

class LLMClient:
    def generate_structured(self, system_prompt: str, user_payload: dict, schema: type[BaseModel]) -> BaseModel:
        if schema.__name__ == "EducatorResponse":
            return schema(summary="Fallback educator summary.", key_points=["Review the result.", "Confirm before proceeding."], choices=["Approve", "Modify", "Repeat"], cautions=[], citations=[])
        if schema.__name__ == "TradeoffResponse":
            return schema(headline="Fallback tradeoff summary.", pros=["Useful engineering direction."], cons=["Further refinement may be needed."], recommendation="Review before continuing.", next_question="Continue or adjust inputs?", citations=[])
        raise ValueError("Unsupported schema")
