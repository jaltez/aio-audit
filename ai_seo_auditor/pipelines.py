import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import scrapy
from itemadapter import ItemAdapter

from ai_seo_auditor.models.schemas import (
    SiteSummary, PageScoreEntry, AggregatedIssue, compute_letter_grade,
    DEFAULT_SCORE_WEIGHTS,
)


class JsonReportPipeline:
    _invalid_filename_chars = re.compile(r"[<>:\"/\\|?*]+")
    _project_root = Path(__file__).resolve().parents[1]

    def open_spider(self, spider: scrapy.Spider) -> None:
        # Determine root domain from the first start_url
        if hasattr(spider, 'start_urls') and spider.start_urls:
            start_url = spider.start_urls[0]
            domain = urlparse(start_url).netloc
        else:
            domain = "unknown_domain"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder_name = f"{domain}_{timestamp}"

        self.reports_dir = self._project_root / "reports" / folder_name
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._page_scores: List[PageScoreEntry] = []
        # Collect all issues across pages for aggregation
        self._all_issues: List[Dict[str, Any]] = []

        spider.logger.info(f"Reports will be saved to {self.reports_dir}")

    def process_item(self, item: Any, spider: scrapy.Spider) -> Any:
        adapter = ItemAdapter(item)
        url = adapter.get("url", "unknown_url")
        audit_status = adapter.get("audit_status", "complete")

        safe_name = self._build_safe_filename(url)
        filename = self.reports_dir / f"{safe_name}.json"

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(adapter.asdict(), f, indent=2, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            spider.logger.error(f"Failed to serialize report for {url}: {e}")
            return item

        # Collect per-page scores
        ops = adapter.get("onpage_seo", {}).get("score", 0)
        sch = adapter.get("schema_analysis", {}).get("score", 0)
        cnt = adapter.get("content_analysis", {}).get("score", 0)
        lnk = adapter.get("link_analysis", {}).get("score", 0)
        prf = adapter.get("performance", {}).get("score", 0)
        rda = adapter.get("readability", {}).get("score", 0)
        sec = adapter.get("security", {}).get("score", 0)
        a11 = adapter.get("accessibility", {}).get("score", 0)
        can = adapter.get("canonical_analysis", {}).get("score", 0)

        # Compute overall score using weights
        scores_dict = {
            "onpage_seo": ops,
            "schema_analysis": sch,
            "content_analysis": cnt,
            "link_analysis": lnk,
            "performance": prf,
            "readability": rda,
            "security": sec,
            "accessibility": a11,
        }
        overall = round(sum(scores_dict[k] * DEFAULT_SCORE_WEIGHTS[k] for k in DEFAULT_SCORE_WEIGHTS), 1)

        # Count issues for this page — collect from all dimensions that have issues
        issues_count = 0
        for section_key in ("onpage_seo", "content_analysis", "link_analysis", "readability", "accessibility"):
            section_issues = adapter.get(section_key, {}).get("issues", [])
            issues_count += len(section_issues)
            for issue in section_issues:
                self._all_issues.append({
                    "description": issue.get("description", ""),
                    "severity": issue.get("severity", "medium"),
                    "url": url,
                })

        entry = PageScoreEntry(
            url=url,
            audit_status=audit_status,
            onpage_seo_score=ops,
            schema_score=sch,
            content_score=cnt,
            link_score=lnk,
            performance_score=prf,
            readability_score=rda,
            security_score=sec,
            accessibility_score=a11,
            canonical_score=can,
            overall_score=overall,
            letter_grade=compute_letter_grade(overall),
            issues_count=issues_count,
        )
        self._page_scores.append(entry)

        spider.logger.info(f"Saved audit report for {url} to {filename}")
        return item

    def close_spider(self, spider: scrapy.Spider) -> None:
        """Write an aggregate site summary report."""
        try:
            if not self._page_scores:
                spider.logger.warning("No page scores collected — skipping site summary.")
                return

            total = len(self._page_scores)

            # Only include complete/partial audits in averages (exclude failed)
            valid_pages = [p for p in self._page_scores if p.audit_status != "failed"]
            valid_count = len(valid_pages) or 1  # avoid div-by-zero

            # Dimension averages
            dim_keys = [
                ("onpage_seo_score", "onpage_seo"),
                ("schema_score", "schema_analysis"),
                ("content_score", "content_analysis"),
                ("link_score", "link_analysis"),
                ("performance_score", "performance"),
                ("readability_score", "readability"),
                ("security_score", "security"),
                ("accessibility_score", "accessibility"),
                ("canonical_score", "canonical_analysis"),
            ]
            dimension_averages = {}
            for attr, label in dim_keys:
                dimension_averages[label] = round(
                    sum(getattr(p, attr) for p in valid_pages) / valid_count, 1
                )

            overall_avg = round(
                sum(p.overall_score for p in valid_pages) / valid_count, 1
            )

            # Best / worst pages (by overall_score)
            sorted_pages = sorted(self._page_scores, key=lambda p: p.overall_score)
            worst_pages = sorted_pages[:3]
            best_pages = sorted_pages[-3:][::-1]

            # Severity distribution
            severity_dist: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
            for issue in self._all_issues:
                sev = issue.get("severity", "medium")
                if sev in severity_dist:
                    severity_dist[sev] += 1

            # Aggregate top issues — group by description, count occurrences
            issue_counter: Counter = Counter()
            issue_severity: Dict[str, str] = {}
            issue_pages: Dict[str, List[str]] = {}
            for issue in self._all_issues:
                desc = issue["description"]
                issue_counter[desc] += 1
                issue_severity.setdefault(desc, issue["severity"])
                issue_pages.setdefault(desc, []).append(issue["url"])

            top_issues = [
                AggregatedIssue(
                    description=desc,
                    severity=issue_severity[desc],
                    count=count,
                    affected_pages=list(dict.fromkeys(issue_pages[desc])),  # unique, ordered
                )
                for desc, count in issue_counter.most_common(20)
            ]

            summary = SiteSummary(
                pages_audited=total,
                overall_grade=compute_letter_grade(overall_avg),
                overall_score=overall_avg,
                dimension_averages=dimension_averages,
                severity_distribution=severity_dist,
                best_pages=best_pages,
                worst_pages=worst_pages,
                top_issues=top_issues,
                pages=sorted_pages,
            )

            summary_path = self.reports_dir / "_site_summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False, default=str)
            spider.logger.info(f"Site summary saved to {summary_path}")
        except Exception as e:
            spider.logger.error(f"Failed to write site summary: {e}", exc_info=True)

    def _build_safe_filename(self, url: str) -> str:
        sanitized = self._invalid_filename_chars.sub("_", url)
        sanitized = sanitized.replace("http://", "").replace("https://", "")
        sanitized = sanitized.replace(" ", "_")
        sanitized = re.sub(r"_+", "_", sanitized).strip("._-") or "report"

        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
        max_base_length = 180
        if len(sanitized) > max_base_length:
            sanitized = sanitized[:max_base_length].rstrip("._-")

        return f"{sanitized}-{url_hash}"
