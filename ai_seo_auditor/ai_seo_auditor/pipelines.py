import json
import time
from pathlib import Path
from itemadapter import ItemAdapter

class JsonReportPipeline:
    def open_spider(self, spider):
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        url = adapter.get("url", "unknown_url")

        # Simple sanitization of URL for filename
        safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "")
        timestamp = int(time.time())
        filename = self.reports_dir / f"{safe_name}_{timestamp}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(adapter.asdict(), f, indent=2, ensure_ascii=False)

        spider.logger.info(f"Saved audit report for {url} to {filename}")
        return item
