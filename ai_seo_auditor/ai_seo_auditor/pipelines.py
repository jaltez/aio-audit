import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from itemadapter import ItemAdapter

class JsonReportPipeline:
    _invalid_filename_chars = re.compile(r"[<>:\"/\\|?*]+")

    def open_spider(self, spider):
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

        spider.logger.info(f"Reports will be saved to {self.reports_dir}")

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        url = adapter.get("url", "unknown_url")

        safe_name = self._build_safe_filename(url)

        filename = self.reports_dir / f"{safe_name}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(adapter.asdict(), f, indent=2, ensure_ascii=False)

        spider.logger.info(f"Saved audit report for {url} to {filename}")
        return item

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
