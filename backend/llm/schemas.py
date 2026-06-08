from pydantic import BaseModel, Field
from typing import List, Optional

class Citation(BaseModel):
    source: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    url: Optional[str] = None

class EducatorResponse(BaseModel):
    summary: str
    key_points: List[str]
    choices: List[str]
    cautions: List[str]
    citations: List[Citation] = Field(default_factory=list)

class TradeoffResponse(BaseModel):
    headline: str
    pros: List[str]
    cons: List[str]
    recommendation: str
    next_question: str
    citations: List[Citation] = Field(default_factory=list)
