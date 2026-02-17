from __future__ import annotations

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from typing import Any, Dict, List, Literal, Optional


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class Issue(BaseModel):
    severity: Literal["high", "medium", "low"] = Field(
        ..., description="high, medium, or low"
    )
    description: str
    suggested_fix: str


# ---------------------------------------------------------------------------
# Spider-extracted structural models
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Scored base
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Original three LLM-scored dimensions
# ---------------------------------------------------------------------------

class SemanticScore(_ScoredModel):
    issues: List[Issue]


class SchemaScore(_ScoredModel):
    detected_types: List[str]
    missing_fields: List[str]

    @model_validator(mode="after")
    def enforce_zero_score_when_no_types(self) -> SchemaScore:
        """If no JSON-LD schemas were detected the score must be 0."""
        if not self.detected_types and self.score != 0:
            self.score = 0
        return self


class ContentScore(_ScoredModel):
    has_direct_answer: bool
    answer_snippet: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# NEW dimension — Link Analysis (spider counts + LLM qualitative score)
# ---------------------------------------------------------------------------

class LinkAnalysis(_ScoredModel):
    """Internal/external link metrics. Spider populates counts; LLM scores
    anchor-text quality and link distribution."""
    internal_links: int = 0
    external_links: int = 0
    nofollow_count: int = 0
    broken_links: List[str] = Field(default_factory=list)
    issues: List[Issue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# NEW dimension — Performance (fully spider-computed)
# ---------------------------------------------------------------------------

class PerformanceMetrics(_ScoredModel):
    """Page-load performance derived from Scrapy response metadata.
    Score is auto-computed — the LLM does NOT produce this."""
    response_time_ms: int = 0
    page_size_bytes: int = 0
    resource_count: int = 0

    @model_validator(mode="after")
    def auto_score(self) -> PerformanceMetrics:
        """Compute score from response time and page size.

        Response-time component (60 % weight):
            <=  500 ms → 100
            <= 1000 ms →  80
            <= 2000 ms →  60
            <= 4000 ms →  30
            >  4000 ms →   0

        Page-size component (40 % weight):
            <= 200 KB → 100
            <= 500 KB →  80
            <= 1 MB   →  60
            <= 3 MB   →  30
            >  3 MB   →   0
        """
        # Response-time tiers
        rt = self.response_time_ms
        if rt <= 500:
            rt_score = 100
        elif rt <= 1000:
            rt_score = 80
        elif rt <= 2000:
            rt_score = 60
        elif rt <= 4000:
            rt_score = 30
        else:
            rt_score = 0

        # Page-size tiers (bytes)
        ps = self.page_size_bytes
        if ps <= 200_000:
            ps_score = 100
        elif ps <= 500_000:
            ps_score = 80
        elif ps <= 1_000_000:
            ps_score = 60
        elif ps <= 3_000_000:
            ps_score = 30
        else:
            ps_score = 0

        self.score = round(rt_score * 0.6 + ps_score * 0.4)
        return self


# ---------------------------------------------------------------------------
# NEW dimension — Readability (spider word-count + LLM qualitative)
# ---------------------------------------------------------------------------

class ReadabilityAnalysis(_ScoredModel):
    """Text readability assessment. word_count and thin_content are
    spider-populated; reading_level and keyword_density_notes come from LLM."""
    word_count: int = 0
    reading_level: Optional[str] = None
    keyword_density_notes: Optional[str] = None
    thin_content: bool = False
    issues: List[Issue] = Field(default_factory=list)

    @model_validator(mode="after")
    def flag_thin_content(self) -> ReadabilityAnalysis:
        if self.word_count < 300:
            self.thin_content = True
        return self


# ---------------------------------------------------------------------------
# NEW dimension — Security (fully spider-computed)
# ---------------------------------------------------------------------------

class SecurityCheck(_ScoredModel):
    """Security header inspection. Entirely computed by the spider."""
    is_https: bool = False
    has_hsts: bool = False
    has_csp: bool = False
    has_x_content_type: bool = False
    mixed_content_urls: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def auto_score(self) -> SecurityCheck:
        """Score breakdown:
        - HTTPS: 40 pts
        - HSTS:  20 pts
        - CSP:   20 pts
        - X-Content-Type-Options: 10 pts
        - No mixed content: 10 pts
        """
        s = 0
        if self.is_https:
            s += 40
        if self.has_hsts:
            s += 20
        if self.has_csp:
            s += 20
        if self.has_x_content_type:
            s += 10
        if not self.mixed_content_urls:
            s += 10
        self.score = s
        return self


# ---------------------------------------------------------------------------
# NEW dimension — Accessibility basics (spider counts + LLM issues)
# ---------------------------------------------------------------------------

class AccessibilityAnalysis(_ScoredModel):
    """Basic accessibility signals. Spider extracts structural data;
    LLM provides qualitative issues and score."""
    has_skip_nav: bool = False
    aria_landmark_count: int = 0
    form_labels_missing: int = 0
    issues: List[Issue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# NEW dimension — Canonical / redirect (fully spider-computed)
# ---------------------------------------------------------------------------

class CanonicalAnalysis(_ScoredModel):
    """Canonical URL correctness and redirect chain analysis."""
    canonical_url: Optional[str] = None
    matches_actual_url: bool = True
    redirect_chain: List[str] = Field(default_factory=list)
    has_hreflang: bool = False

    @model_validator(mode="after")
    def auto_score(self) -> CanonicalAnalysis:
        """Score breakdown:
        - Canonical present & matches: 50 pts
        - Canonical present but mismatch: 20 pts
        - No canonical: 0 pts from this component
        - No redirect chain (direct access): 30 pts
        - Short redirect chain (1 hop): 20 pts
        - Long chain (2+): 0 pts
        - hreflang present: 20 pts
        """
        s = 0
        if self.canonical_url:
            s += 50 if self.matches_actual_url else 20
        # Redirect chain
        chain_len = len(self.redirect_chain)
        if chain_len == 0:
            s += 30
        elif chain_len == 1:
            s += 20
        # hreflang
        if self.has_hreflang:
            s += 20
        self.score = min(s, 100)
        return self


# ---------------------------------------------------------------------------
# Score weights for overall grade
# ---------------------------------------------------------------------------

DEFAULT_SCORE_WEIGHTS: Dict[str, float] = {
    "semantic_analysis": 0.20,
    "schema_analysis": 0.10,
    "content_analysis": 0.15,
    "link_analysis": 0.15,
    "performance": 0.10,
    "readability": 0.10,
    "security": 0.10,
    "accessibility": 0.10,
}


def compute_letter_grade(score: float) -> str:
    """Map a 0-100 numeric score to an A–F letter grade."""
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Root page audit model
# ---------------------------------------------------------------------------

class PageAudit(BaseModel):
    url: str
    meta_tags: MetaTags
    headers: HeaderStructure
    image_stats: ImageStats
    # Original dimensions
    semantic_analysis: SemanticScore
    schema_analysis: SchemaScore
    content_analysis: ContentScore
    # New dimensions
    link_analysis: LinkAnalysis
    performance: PerformanceMetrics
    readability: ReadabilityAnalysis
    security: SecurityCheck
    accessibility: AccessibilityAnalysis
    canonical_analysis: CanonicalAnalysis

    @computed_field  # type: ignore[misc]
    @property
    def overall_score(self) -> float:
        """Weighted average of all dimension scores."""
        scores = {
            "semantic_analysis": self.semantic_analysis.score,
            "schema_analysis": self.schema_analysis.score,
            "content_analysis": self.content_analysis.score,
            "link_analysis": self.link_analysis.score,
            "performance": self.performance.score,
            "readability": self.readability.score,
            "security": self.security.score,
            "accessibility": self.accessibility.score,
        }
        total = sum(
            scores[k] * DEFAULT_SCORE_WEIGHTS[k] for k in DEFAULT_SCORE_WEIGHTS
        )
        return round(total, 1)

    @computed_field  # type: ignore[misc]
    @property
    def letter_grade(self) -> str:
        return compute_letter_grade(self.overall_score)


# ---------------------------------------------------------------------------
# Site-level summary model
# ---------------------------------------------------------------------------

class PageScoreEntry(BaseModel):
    url: str
    semantic_score: int = 0
    schema_score: int = 0
    content_score: int = 0
    link_score: int = 0
    performance_score: int = 0
    readability_score: int = 0
    security_score: int = 0
    accessibility_score: int = 0
    canonical_score: int = 0
    overall_score: float = 0.0
    letter_grade: str = "F"
    issues_count: int = 0


class AggregatedIssue(BaseModel):
    description: str
    severity: Literal["high", "medium", "low"]
    count: int = 1
    affected_pages: List[str] = Field(default_factory=list)


class SiteSummary(BaseModel):
    pages_audited: int = 0
    overall_grade: str = "F"
    overall_score: float = 0.0
    dimension_averages: Dict[str, float] = Field(default_factory=dict)
    severity_distribution: Dict[str, int] = Field(
        default_factory=lambda: {"high": 0, "medium": 0, "low": 0}
    )
    best_pages: List[PageScoreEntry] = Field(default_factory=list)
    worst_pages: List[PageScoreEntry] = Field(default_factory=list)
    top_issues: List[AggregatedIssue] = Field(default_factory=list)
    pages: List[PageScoreEntry] = Field(default_factory=list)
