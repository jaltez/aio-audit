from pydantic import BaseModel, Field
from typing import List, Optional

class Issue(BaseModel):
    severity: str = Field(..., description="high, medium, or low")
    description: str
    suggested_fix: str

class SemanticScore(BaseModel):
    score: int = Field(..., description="0 to 100")
    issues: List[Issue]

class SchemaScore(BaseModel):
    score: int
    detected_types: List[str]
    missing_fields: List[str]

class ContentScore(BaseModel):
    score: int
    has_direct_answer: bool
    answer_snippet: Optional[str]

class PageAudit(BaseModel):
    url: str
    semantic_analysis: SemanticScore
    schema_analysis: SchemaScore
    content_analysis: ContentScore
