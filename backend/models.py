from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AuditStatus = Literal["complete", "partial", "failed"]


class SessionInfo(BaseModel):
    id: str
    created_at: datetime
    pages_count: int
    has_summary: bool


class PageSummary(BaseModel):
    page_id: str
    url: str
    audit_status: AuditStatus = "complete"
    onpage_seo_score: float = 0
    schema_score: float = 0
    content_score: float = 0
    link_score: float = 0
    performance_score: float = 0
    readability_score: float = 0
    security_score: float = 0
    accessibility_score: float = 0
    canonical_score: float = 0
    overall_score: float = 0
    letter_grade: str = "F"
    issues_count: int = 0
    risk_index: float = 0


class SeverityDistribution(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0


class TopIssue(BaseModel):
    description: str
    severity: Literal["high", "medium", "low"] = "medium"
    count: int
    affected_pages: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    overall_score: float
    overall_grade: str
    dimension_averages: dict[str, float]
    severity_distribution: SeverityDistribution
    top_issues: list[TopIssue]
    best_pages: list[PageSummary]
    worst_pages: list[PageSummary]


class PaginatedPages(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PageSummary]


class PageDetail(BaseModel):
    summary: PageSummary
    raw_data: dict[str, Any]

