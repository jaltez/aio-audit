from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from backend.models import (
    PageSummary,
    SessionInfo,
    SessionSummary,
    SeverityDistribution,
    TopIssue,
)

DIMENSION_KEYS = [
    "onpage_seo_score",
    "schema_score",
    "content_score",
    "link_score",
    "performance_score",
    "readability_score",
    "security_score",
    "accessibility_score",
]

ISSUE_SECTIONS = [
    "onpage_seo",
    "content_analysis",
    "link_analysis",
    "readability",
    "accessibility",
    "security",
]

SUMMARY_DIMENSION_MAP = {
    "onpage_seo_score": "onpage_seo",
    "schema_score": "schema_analysis",
    "content_score": "content_analysis",
    "link_score": "link_analysis",
    "performance_score": "performance",
    "readability_score": "readability",
    "security_score": "security",
    "accessibility_score": "accessibility",
}


def grade_from_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


@dataclass
class PageRecord:
    page_id: str
    source_path: Path
    raw_data: dict[str, Any]
    summary: PageSummary


class ReportStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.reports_root = self._resolve_reports_root()

    def _resolve_reports_root(self) -> Path:
        root_reports = self.project_root / "reports"
        legacy_reports = self.project_root / "ai_seo_auditor" / "reports"
        if root_reports.exists():
            return root_reports
        return legacy_reports

    def list_sessions(self) -> list[SessionInfo]:
        if not self.reports_root.exists():
            return []

        sessions: list[SessionInfo] = []
        for folder in sorted(self.reports_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not folder.is_dir():
                continue

            page_files = [p for p in folder.glob("*.json") if not p.name.startswith("_")]
            if not page_files:
                continue

            sessions.append(
                SessionInfo(
                    id=folder.name,
                    created_at=datetime.fromtimestamp(folder.stat().st_mtime),
                    pages_count=len(page_files),
                    has_summary=(folder / "_site_summary.json").exists(),
                )
            )
        return sessions

    def get_session_path(self, session_id: str) -> Path:
        path = self.reports_root / session_id
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"Session not found: {session_id}")
        return path

    def load_pages(self, session_id: str) -> list[PageRecord]:
        session_path = self.get_session_path(session_id)
        records: list[PageRecord] = []
        for page_file in sorted(session_path.glob("*.json")):
            if page_file.name.startswith("_"):
                continue

            try:
                with open(page_file, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception:
                continue

            raw = self._migrate_legacy_shape(raw)
            summary = self._normalize_page(page_file, raw)
            records.append(PageRecord(page_id=summary.page_id, source_path=page_file, raw_data=raw, summary=summary))

        return records

    @staticmethod
    def _migrate_legacy_shape(report: dict[str, Any]) -> dict[str, Any]:
        if "semantic_analysis" in report and "onpage_seo" not in report:
            report["onpage_seo"] = report.pop("semantic_analysis")

        perf = report.get("performance", {})
        if "response_time_ms" in perf and "ttfb_ms" not in perf:
            perf["ttfb_ms"] = perf["response_time_ms"]
            perf.setdefault("fcp_ms", None)
            perf.setdefault("dom_content_loaded_ms", None)

        report.setdefault("audit_status", "complete")
        return report

    @staticmethod
    def _normalize_page(page_path: Path, report: dict[str, Any]) -> PageSummary:
        issues_count = sum(len(report.get(section, {}).get("issues", [])) for section in ISSUE_SECTIONS)
        overall = float(report.get("overall_score", 0))
        risk_index = round(((100 - max(0.0, min(100.0, overall))) * 0.65) + (min(issues_count, 20) * 5 * 0.35), 1)

        return PageSummary(
            page_id=page_path.stem,
            url=report.get("url", page_path.stem),
            audit_status=report.get("audit_status", "complete"),
            onpage_seo_score=float(report.get("onpage_seo", {}).get("score", 0)),
            schema_score=float(report.get("schema_analysis", {}).get("score", 0)),
            content_score=float(report.get("content_analysis", {}).get("score", 0)),
            link_score=float(report.get("link_analysis", {}).get("score", 0)),
            performance_score=float(report.get("performance", {}).get("score", 0)),
            readability_score=float(report.get("readability", {}).get("score", 0)),
            security_score=float(report.get("security", {}).get("score", 0)),
            accessibility_score=float(report.get("accessibility", {}).get("score", 0)),
            canonical_score=float(report.get("canonical_analysis", {}).get("score", 0)),
            overall_score=overall,
            letter_grade=report.get("letter_grade", grade_from_score(overall)),
            issues_count=issues_count,
            risk_index=risk_index,
        )

    def load_summary(self, session_id: str, pages: list[PageRecord]) -> SessionSummary:
        session_path = self.get_session_path(session_id)
        summary_path = session_path / "_site_summary.json"
        if summary_path.exists():
            with open(summary_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            return self._summary_from_file(loaded, pages)
        return self._summary_from_pages(pages)

    def _summary_from_file(self, loaded: dict[str, Any], pages: list[PageRecord]) -> SessionSummary:
        top_issues = [
            TopIssue(
                description=item.get("description", ""),
                severity=item.get("severity", "medium"),
                count=int(item.get("count", 0)),
                affected_pages=item.get("affected_pages", []),
            )
            for item in loaded.get("top_issues", [])
        ]
        best_pages = self._best_or_worst_pages(pages, reverse=True)
        worst_pages = self._best_or_worst_pages(pages, reverse=False)
        return SessionSummary(
            overall_score=float(loaded.get("overall_score", 0)),
            overall_grade=loaded.get("overall_grade", grade_from_score(float(loaded.get("overall_score", 0)))),
            dimension_averages={
                k: float(v)
                for k, v in (loaded.get("dimension_averages", {}) or {}).items()
            },
            severity_distribution=SeverityDistribution.model_validate(loaded.get("severity_distribution", {})),
            top_issues=top_issues,
            best_pages=best_pages,
            worst_pages=worst_pages,
        )

    def _summary_from_pages(self, pages: list[PageRecord]) -> SessionSummary:
        scored_pages = [p.summary for p in pages if p.summary.audit_status != "failed"] or [p.summary for p in pages]

        if not scored_pages:
            return SessionSummary(
                overall_score=0,
                overall_grade="F",
                dimension_averages={},
                severity_distribution=SeverityDistribution(),
                top_issues=[],
                best_pages=[],
                worst_pages=[],
            )

        overall_score = round(sum(p.overall_score for p in scored_pages) / len(scored_pages), 1)
        dim_averages: dict[str, float] = {}
        for key in DIMENSION_KEYS:
            dim_averages[SUMMARY_DIMENSION_MAP[key]] = round(
                sum(getattr(p, key) for p in scored_pages) / len(scored_pages), 1
            )

        severity_counts = defaultdict(int)
        issue_map: dict[tuple[str, str], set[str]] = defaultdict(set)
        for rec in pages:
            for issue in iter_issues(rec.raw_data):
                severity = issue.get("severity", "medium").lower()
                if severity not in ("high", "medium", "low"):
                    severity = "medium"
                description = issue.get("description", "")
                severity_counts[severity] += 1
                issue_map[(description, severity)].add(rec.summary.url)

        top_issues: list[TopIssue] = []
        for (description, severity), affected_pages in sorted(
            issue_map.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )[:15]:
            top_issues.append(
                TopIssue(
                    description=description,
                    severity=severity,
                    count=len(affected_pages),
                    affected_pages=sorted(affected_pages),
                )
            )

        return SessionSummary(
            overall_score=overall_score,
            overall_grade=grade_from_score(overall_score),
            dimension_averages=dim_averages,
            severity_distribution=SeverityDistribution(
                high=severity_counts["high"],
                medium=severity_counts["medium"],
                low=severity_counts["low"],
            ),
            top_issues=top_issues,
            best_pages=self._best_or_worst_pages(pages, reverse=True),
            worst_pages=self._best_or_worst_pages(pages, reverse=False),
        )

    @staticmethod
    def _best_or_worst_pages(pages: list[PageRecord], *, reverse: bool) -> list[PageSummary]:
        sorted_pages = sorted(pages, key=lambda p: p.summary.overall_score, reverse=reverse)
        return [p.summary for p in sorted_pages[:3]]


def iter_issues(raw_page: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for section in ISSUE_SECTIONS:
        for issue in raw_page.get(section, {}).get("issues", []):
            if isinstance(issue, dict):
                yield issue

