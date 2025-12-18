import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from itemadapter import ItemAdapter

class JsonReportPipeline:
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

        # Simple sanitization of URL for filename
        safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "")
        # Remove potentially too long filename issues if needed, or keep it simple
        if len(safe_name) > 200:
            safe_name = safe_name[:200]

        filename = self.reports_dir / f"{safe_name}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(adapter.asdict(), f, indent=2, ensure_ascii=False)

        spider.logger.info(f"Saved audit report for {url} to {filename}")
        return item
