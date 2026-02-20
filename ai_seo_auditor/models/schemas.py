from __future__ import annotations

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from typing import Any, Dict, List, Literal, Optional


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class Issue(BaseModel):
    severity: Literal["high", "medium", "low"] = Field(
        ..., description=(
            "high = blocks indexing or renders page unusable for search/screen readers; "
            "medium = degrades ranking potential or user experience; "
            "low = optimization opportunity"
        ),
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
# Dimension 1 — On-Page SEO (fully spider-computed, replaces semantic_analysis)
# ---------------------------------------------------------------------------

class OnPageSeoChecklist(_ScoredModel):
    """Deterministic on-page SEO checklist. Fully spider-computed.
    Score is auto-calculated from pass/fail checks."""
    has_title: bool = False
    title_length_ok: bool = False           # 30-60 chars
    title_length: int = 0
    has_meta_description: bool = False
    description_length_ok: bool = False     # 70-160 chars
    description_length: int = 0
    single_h1: bool = False
    h1_count: int = 0
    has_viewport_meta: bool = False
    has_lang_attribute: bool = False
    has_og_tags: bool = False               # at least og:title and og:description
    robots_allows_indexing: bool = True     # True unless robots meta says noindex
    image_alt_coverage_pct: float = 100.0   # % of images with non-empty alt
    has_canonical: bool = False
    issues: List[Issue] = Field(default_factory=list)

    @model_validator(mode="after")
    def auto_score(self) -> OnPageSeoChecklist:
        """Point-based scoring (max 100):
        - has_title:               10 pts
        - title_length_ok:         10 pts
        - has_meta_description:    10 pts
        - description_length_ok:    5 pts
        - single_h1:              10 pts
        - has_viewport_meta:        5 pts
        - has_lang_attribute:      10 pts
        - has_og_tags:              5 pts
        - robots_allows_indexing:  10 pts
        - image_alt_coverage:      15 pts (proportional)
        - has_canonical:           10 pts
        """
        s = 0
        if self.has_title:
            s += 10
        if self.title_length_ok:
            s += 10
        if self.has_meta_description:
            s += 10
        if self.description_length_ok:
            s += 5
        if self.single_h1:
            s += 10
        if self.has_viewport_meta:
            s += 5
        if self.has_lang_attribute:
            s += 10
        if self.has_og_tags:
            s += 5
        if self.robots_allows_indexing:
            s += 10
        # Image alt coverage: proportional 0-15 pts
        s += round(self.image_alt_coverage_pct / 100.0 * 15)
        if self.has_canonical:
            s += 10
        self.score = min(s, 100)
        return self


# ---------------------------------------------------------------------------
# Dimension 2 — Schema Analysis (LLM-scored with business rules)
# ---------------------------------------------------------------------------

class SchemaScore(_ScoredModel):
    detected_types: List[str]
    missing_fields: List[str]

    @model_validator(mode="after")
    def enforce_zero_score_when_no_types(self) -> SchemaScore:
        """If no JSON-LD schemas were detected the score must be 0."""
        if not self.detected_types and self.score != 0:
            self.score = 0
        return self


# ---------------------------------------------------------------------------
# Dimension 3 — Content Analysis (LLM-scored, redefined criteria)
# ---------------------------------------------------------------------------

class ContentScore(_ScoredModel):
    answers_user_intent: bool = False
    content_uniqueness_note: Optional[str] = Field(
        default=None, max_length=500,
        description="LLM assessment of boilerplate vs. original content ratio",
    )
    answer_snippet: Optional[str] = Field(default=None, max_length=500)
    issues: List[Issue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dimension 4 — Link Analysis (spider counts + LLM qualitative score)
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
# Dimension 5 — Performance (fully spider-computed, enhanced with Playwright timing)
# ---------------------------------------------------------------------------

class PerformanceMetrics(_ScoredModel):
    """Page-load performance from Playwright timing + Scrapy metadata.
    Score is auto-computed — the LLM does NOT produce this."""
    ttfb_ms: int = 0               # Time to First Byte (responseStart - navigationStart)
    fcp_ms: Optional[int] = None   # First Contentful Paint
    dom_content_loaded_ms: int = 0  # DOMContentLoaded event
    page_size_bytes: int = 0
    resource_count: int = 0

    @model_validator(mode="after")
    def auto_score(self) -> PerformanceMetrics:
        """Score using Web Vitals-aligned thresholds.

        TTFB (25% weight): ≤800ms=100, ≤1800ms=50, >1800ms=0
        FCP  (25% weight): ≤1800ms=100, ≤3000ms=50, >3000ms=0 (or 50 if unavailable)
        Page size (25% weight): ≤500KB=100, ≤1MB=75, ≤2MB=50, >2MB=25
        Resource count (25% weight): ≤30=100, ≤60=75, ≤100=50, >100=25
        """
        # TTFB tiers
        ttfb = self.ttfb_ms
        if ttfb <= 800:
            ttfb_score = 100
        elif ttfb <= 1800:
            ttfb_score = 50
        else:
            ttfb_score = 0

        # FCP tiers
        fcp = self.fcp_ms
        if fcp is not None:
            if fcp <= 1800:
                fcp_score = 100
            elif fcp <= 3000:
                fcp_score = 50
            else:
                fcp_score = 0
        else:
            fcp_score = 50  # neutral if FCP unavailable

        # Page size tiers
        ps = self.page_size_bytes
        if ps <= 500_000:
            ps_score = 100
        elif ps <= 1_000_000:
            ps_score = 75
        elif ps <= 2_000_000:
            ps_score = 50
        else:
            ps_score = 25

        # Resource count tiers
        rc = self.resource_count
        if rc <= 30:
            rc_score = 100
        elif rc <= 60:
            rc_score = 75
        elif rc <= 100:
            rc_score = 50
        else:
            rc_score = 25

        self.score = round(
            ttfb_score * 0.25
            + fcp_score * 0.25
            + ps_score * 0.25
            + rc_score * 0.25
        )
        return self


# ---------------------------------------------------------------------------
# Dimension 6 — Readability (fully spider-computed, Flesch-Kincaid)
# ---------------------------------------------------------------------------

class ReadabilityAnalysis(_ScoredModel):
    """Deterministic readability assessment using Flesch-Kincaid.
    Fully spider-computed — the LLM does NOT produce this."""
    word_count: int = 0
    sentence_count: int = 0
    syllable_count: int = 0
    avg_sentence_length: float = 0.0
    avg_syllables_per_word: float = 0.0
    flesch_reading_ease: float = 0.0       # 0-100 scale (higher = easier)
    flesch_kincaid_grade: float = 0.0      # US grade level
    reading_level: str = "Unknown"          # e.g. "Grade 8"
    thin_content: bool = False
    issues: List[Issue] = Field(default_factory=list)

    @model_validator(mode="after")
    def auto_score(self) -> ReadabilityAnalysis:
        """Map Flesch Reading Ease to audit score.
        FRE >= 60 → 100 (accessible for general web)
        FRE 50-59 → 80
        FRE 40-49 → 60
        FRE 30-39 → 40
        FRE < 30  → 20
        Thin content (<300 words) caps at 50.
        """
        if self.word_count < 300:
            self.thin_content = True

        fre = self.flesch_reading_ease
        if fre >= 60:
            s = 100
        elif fre >= 50:
            s = 80
        elif fre >= 40:
            s = 60
        elif fre >= 30:
            s = 40
        else:
            s = 20

        if self.thin_content:
            s = min(s, 50)

        self.score = s
        return self


# ---------------------------------------------------------------------------
# Dimension 7 — Security (fully spider-computed)
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
# Dimension 8 — Accessibility (spider deterministic base + LLM qualitative)
# ---------------------------------------------------------------------------

class AccessibilityAnalysis(_ScoredModel):
    """Accessibility signals. Spider extracts structural data (deterministic
    base score 50%); LLM provides qualitative issues and score (50%)."""
    # Deterministic spider checks
    has_skip_nav: bool = False
    aria_landmark_count: int = 0
    form_labels_missing: int = 0
    has_lang_attribute: bool = False
    image_alt_coverage_pct: float = 100.0
    generic_link_text_count: int = 0        # "click here", "read more", etc.
    has_heading_structure: bool = False      # at least one heading exists
    tabindex_misuse_count: int = 0          # elements with tabindex > 0
    has_document_title: bool = False
    # LLM-provided
    issues: List[Issue] = Field(default_factory=list)
    llm_score: Optional[int] = Field(
        default=None,
        description="LLM's qualitative accessibility score (0-100)",
    )

    @field_validator("llm_score", mode="before")
    @classmethod
    def coerce_llm_score(cls, v: object) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, float):
            v = round(v)
        if isinstance(v, int) and 0 <= v <= 100:
            return v
        return None

    @model_validator(mode="after")
    def compute_blended_score(self) -> AccessibilityAnalysis:
        """Blend deterministic checklist (50%) with LLM qualitative (50%).

        Deterministic checklist (max 100):
        - has_skip_nav:           15 pts
        - has_lang_attribute:     15 pts
        - has_document_title:     10 pts
        - has_heading_structure:  10 pts
        - image_alt_coverage:     20 pts (proportional)
        - form_labels_missing:    10 pts (0 missing = 10, any missing = 0)
        - no generic link text:   10 pts (0 found = 10, any = 0)
        - no tabindex misuse:     10 pts (0 misuse = 10, any = 0)
        """
        det = 0
        if self.has_skip_nav:
            det += 15
        if self.has_lang_attribute:
            det += 15
        if self.has_document_title:
            det += 10
        if self.has_heading_structure:
            det += 10
        det += round(self.image_alt_coverage_pct / 100.0 * 20)
        if self.form_labels_missing == 0:
            det += 10
        if self.generic_link_text_count == 0:
            det += 10
        if self.tabindex_misuse_count == 0:
            det += 10

        llm = self.llm_score if self.llm_score is not None else det
        self.score = round(det * 0.5 + llm * 0.5)
        return self


# ---------------------------------------------------------------------------
# Bonus — Canonical / redirect (fully spider-computed, not in weighted avg)
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
        chain_len = len(self.redirect_chain)
        if chain_len == 0:
            s += 30
        elif chain_len == 1:
            s += 20
        if self.has_hreflang:
            s += 20
        self.score = min(s, 100)
        return self


# ---------------------------------------------------------------------------
# Score weights for overall grade
# ---------------------------------------------------------------------------

DEFAULT_SCORE_WEIGHTS: Dict[str, float] = {
    "onpage_seo": 0.20,
    "schema_analysis": 0.10,
    "content_analysis": 0.15,
    "link_analysis": 0.15,
    "performance": 0.10,
    "readability": 0.10,
    "security": 0.10,
    "accessibility": 0.10,
}


def compute_letter_grade(score: float) -> str:
    """Map a 0-100 numeric score to an A-F letter grade."""
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
    audit_status: Literal["complete", "partial", "failed"] = "complete"
    meta_tags: MetaTags
    headers: HeaderStructure
    image_stats: ImageStats
    # Dimensions
    onpage_seo: OnPageSeoChecklist
    schema_analysis: SchemaScore
    content_analysis: ContentScore
    link_analysis: LinkAnalysis
    performance: PerformanceMetrics
    readability: ReadabilityAnalysis
    security: SecurityCheck
    accessibility: AccessibilityAnalysis
    canonical_analysis: CanonicalAnalysis

    @computed_field  # type: ignore[misc]
    @property
    def overall_score(self) -> float:
        """Weighted average of all 8 dimension scores."""
        scores = {
            "onpage_seo": self.onpage_seo.score,
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
    audit_status: Literal["complete", "partial", "failed"] = "complete"
    onpage_seo_score: int = 0
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
