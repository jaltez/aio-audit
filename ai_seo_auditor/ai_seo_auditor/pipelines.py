import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import scrapy
from itemadapter import ItemAdapter


class JsonReportPipeline:
    _invalid_filename_chars = re.compile(r"[<>:\"/\\|?*]+")

    def open_spider(self, spider: scrapy.Spider) -> None:
        # Determine root domain from the first start_url
        if hasattr(spider, 'start_urls') and spider.start_urls:
            start_url = spider.start_urls[0]
            domain = urlparse(start_url).netloc
        else:
            domain = "unknown_domain"

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder_name = f"{domain}_{timestamp}"

        self.reports_dir = Path("reports") / folder_name
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._page_scores: list[Dict[str, Any]] = []

        spider.logger.info(f"Reports will be saved to {self.reports_dir}")

    def process_item(self, item: Any, spider: scrapy.Spider) -> Any:
        adapter = ItemAdapter(item)
        url = adapter.get("url", "unknown_url")

        safe_name = self._build_safe_filename(url)
        filename = self.reports_dir / f"{safe_name}.json"

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(adapter.asdict(), f, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            spider.logger.error(f"Failed to serialize report for {url}: {e}")
            return item

        # Collect scores for the site summary
        self._page_scores.append({
            "url": url,
            "semantic_score": adapter.get("semantic_analysis", {}).get("score", 0),
            "schema_score": adapter.get("schema_analysis", {}).get("score", 0),
            "content_score": adapter.get("content_analysis", {}).get("score", 0),
        })

        spider.logger.info(f"Saved audit report for {url} to {filename}")
        return item

    def close_spider(self, spider: scrapy.Spider) -> None:
        """Write an aggregate site summary report."""
        if not self._page_scores:
            return

        total = len(self._page_scores)

        def avg_score(key: str) -> float:
            return round(sum(p[key] for p in self._page_scores) / total, 1)

        summary = {
            "pages_audited": total,
            "avg_semantic_score": avg_score("semantic_score"),
            "avg_schema_score": avg_score("schema_score"),
            "avg_content_score": avg_score("content_score"),
            "pages": sorted(self._page_scores, key=lambda p: p["semantic_score"]),
        }

        summary_path = self.reports_dir / "_site_summary.json"
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            spider.logger.info(f"Site summary saved to {summary_path}")
        except (TypeError, ValueError) as e:
            spider.logger.error(f"Failed to write site summary: {e}")

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
