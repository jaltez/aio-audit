from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Literal, Optional


class Issue(BaseModel):
    severity: Literal["high", "medium", "low"] = Field(
        ..., description="high, medium, or low"
    )
    description: str
    suggested_fix: str


class MetaTags(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    canonical: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    robots: Optional[str] = None
    viewport: Optional[str] = None
    og_image: Optional[str] = None
    twitter_card: Optional[str] = None

    @field_validator(
        "title", "description", "og_title", "og_description", mode="before"
    )
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v


class HeaderStructure(BaseModel):
    h1: List[str]
    h2: List[str]
    h3: List[str]
    h4_h6_count: int


class ImageStats(BaseModel):
    total_images: int
    missing_alt: int
    empty_alt: int = 0


class _ScoredModel(BaseModel):
    """Base for models with a 0-100 score field."""

    score: int = Field(..., description="0 to 100")

    @field_validator("score", mode="before")
    @classmethod
    def coerce_and_clamp_score(cls, v: object) -> int:
        """Accept floats from LLMs and coerce to int; enforce 0-100 range."""
        if isinstance(v, float):
            v = round(v)
        if not isinstance(v, int):
            raise TypeError(f"Score must be an integer, got {type(v).__name__}")
        if not 0 <= v <= 100:
            raise ValueError("Score must be between 0 and 100")
        return v


class SemanticScore(_ScoredModel):
    issues: List[Issue]


class SchemaScore(_ScoredModel):
    detected_types: List[str]
    missing_fields: List[str]

    @model_validator(mode="after")
    def enforce_zero_score_when_no_types(self) -> "SchemaScore":
        """If no JSON-LD schemas were detected the score must be 0."""
        if not self.detected_types and self.score != 0:
            self.score = 0
        return self


class ContentScore(_ScoredModel):
    has_direct_answer: bool
    answer_snippet: Optional[str] = Field(default=None, max_length=500)


class PageAudit(BaseModel):
    url: str
    meta_tags: MetaTags
    headers: HeaderStructure
    image_stats: ImageStats
    semantic_analysis: SemanticScore
    schema_analysis: SchemaScore
    content_analysis: ContentScore
