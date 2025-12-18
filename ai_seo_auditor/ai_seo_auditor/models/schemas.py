from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict

class Issue(BaseModel):
    severity: str = Field(..., description="high, medium, or low")
    description: str
    suggested_fix: str

class MetaTags(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    canonical: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None

class HeaderStructure(BaseModel):
    h1: List[str]
    h2: List[str]
    h3: List[str]
    h4_h6_count: int

class ImageStats(BaseModel):
    total_images: int
    missing_alt: int

class SemanticScore(BaseModel):
    score: int = Field(..., description="0 to 100")
    issues: List[Issue]

    @field_validator('score')
    @classmethod
    def score_range(cls, v: int) -> int:
        if not 0 <= v <= 100:
            raise ValueError('Score must be between 0 and 100')
        return v

class SchemaScore(BaseModel):
    score: int
    detected_types: List[str]
    missing_fields: List[str]

    @field_validator('score')
    @classmethod
    def score_range(cls, v: int) -> int:
        if not 0 <= v <= 100:
            raise ValueError('Score must be between 0 and 100')
        return v

class ContentScore(BaseModel):
    score: int
    has_direct_answer: bool
    answer_snippet: Optional[str]

    @field_validator('score')
    @classmethod
    def score_range(cls, v: int) -> int:
        if not 0 <= v <= 100:
            raise ValueError('Score must be between 0 and 100')
        return v

class PageAudit(BaseModel):
    url: str
    meta_tags: MetaTags
    headers: HeaderStructure
    image_stats: ImageStats
    semantic_analysis: SemanticScore
    schema_analysis: SchemaScore
    content_analysis: ContentScore
