import scrapy
import yaml
from pathlib import Path
from scrapy.linkextractors import LinkExtractor
from scrapy_playwright.page import PageMethod
from urllib.parse import urlparse
from ai_seo_auditor.services.llm_service import analyze_with_ollama
from ai_seo_auditor.models.schemas import PageAudit

class AuditSpider(scrapy.Spider):
    name = "audit"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Load config from yaml file located at project root
        # File structure: project_root/ai_seo_auditor/spiders/audit_spider.py
        # Config location: project_root/config.yaml
        config_path = Path(__file__).resolve().parents[2] / 'config.yaml'
        self.config = {}
        if config_path.exists():
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f) or {}
        else:
            self.logger.warning(f"Config file not found at {config_path}. Using defaults.")

        audit_config = self.config.get('audit', {})

        # Get max_depth from kwargs (CLI override) or config, or default to 2
        self.max_depth = int(kwargs.get('max_depth', audit_config.get('max_depth', 2)))

        # Get max_pages from kwargs (CLI override) or config, or default to 10
        self.max_pages = int(kwargs.get('max_pages', audit_config.get('max_pages', 10)))
        self.pages_analyzed = 0

        # Initialize start_urls
        self.start_urls = audit_config.get('start_urls', ["https://books.toscrape.com/"])
        if hasattr(self, "url"):
            self.start_urls = [self.url]

        # Set allowed_domains dynamically based on input URLs
        self.allowed_domains = list({urlparse(url).netloc for url in self.start_urls})

    def start_requests(self):
        self.logger.info(f"Starting audit with max_depth={self.max_depth}")

        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        # Wait for potentially slow dynamic content
                        PageMethod("wait_for_load_state", "networkidle")
                    ],
                }
            )

    async def parse(self, response):
        if self.pages_analyzed >= self.max_pages:
            self.logger.info(f"Max pages limit ({self.max_pages}) reached. Stopping audit for {response.url} and future pages.")
            return

        self.pages_analyzed += 1
        self.logger.info(f"Auditing {response.url} (Page {self.pages_analyzed}/{self.max_pages})")

        # 1. Prepare Data
        # Truncate HTML strictly to keep within context limits
        # In a real scenario, we'd use BeautifulSoup to clean script/style tags first
        html_snippet = response.css("body").get()
        if html_snippet:
            html_snippet = html_snippet[:15000]
        else:
            html_snippet = ""

        # Extract JSON-LD
        json_ld = response.xpath('//script[@type="application/ld+json"]/text()').getall()

        # Extract text content
        # Simple extraction: strict text from P tags
        text_content = " ".join(response.css("p::text").getall())[:5000]

        # 2. Call AI Service (Async)
        # We pass the raw data to our LLM service wrapper
        try:
            audit_result = await analyze_with_ollama(
                url=response.url,
                html=html_snippet,
                json_ld=json_ld,
                text=text_content
            )

            # 3. Yield the validated Pydantic model
            # We convert to dict for Scrapy pipeline compatibility
            yield audit_result.model_dump()

        except Exception as e:
            self.logger.error(f"Error auditing {response.url}: {e}")

        # 4. Crawl: Extract and follow links if depth allows
        current_depth = response.meta.get('depth', 0)
        if current_depth < self.max_depth:
            # Filter for allowed domains ensures we don't drift off-site automatically (if OffsiteMiddleware is enabled)
            # However, passing allow_domains to LinkExtractor is also good practice
            le = LinkExtractor(allow_domains=self.allowed_domains)
            links = le.extract_links(response)

            for link in links:
                yield scrapy.Request(
                    link.url,
                    callback=self.parse,
                    meta={
                        "playwright": True,
                        "playwright_page_methods": [
                            PageMethod("wait_for_load_state", "networkidle")
                        ],
                    }
                )
