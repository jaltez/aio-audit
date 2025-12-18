import scrapy
import yaml
from pathlib import Path
from scrapy.linkextractors import LinkExtractor
from scrapy_playwright.page import PageMethod
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from ai_seo_auditor.services.llm_service import analyze_with_ollama
from ai_seo_auditor.models.schemas import PageAudit, MetaTags, HeaderStructure, ImageStats

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
        # Use BeautifulSoup to clean HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script, style, svg, noscript, and iframe tags to save tokens
        for tag in soup(["script", "style", "svg", "noscript", "iframe"]):
            tag.decompose()
            
        # Get cleaned HTML snippet (body only)
        body = soup.find("body")
        html_snippet = str(body) if body else str(soup)
        html_snippet = html_snippet[:15000]

        # Extract Meta Tags
        meta_tags = MetaTags(
            title=response.xpath('//title/text()').get(),
            description=response.xpath('//meta[@name="description"]/@content').get(),
            canonical=response.xpath('//link[@rel="canonical"]/@href').get(),
            og_title=response.xpath('//meta[@property="og:title"]/@content').get(),
            og_description=response.xpath('//meta[@property="og:description"]/@content').get()
        )

        # Extract Header Structure
        headers = HeaderStructure(
            h1=response.xpath('//h1/text()').getall(),
            h2=response.xpath('//h2/text()').getall(),
            h3=response.xpath('//h3/text()').getall(),
            h4_h6_count=len(response.xpath('//h4 | //h5 | //h6').getall())
        )

        # Extract Image Stats
        images = response.xpath('//img')
        total_images = len(images)
        missing_alt = len(response.xpath('//img[not(@alt) or @alt=""]').getall())
        image_stats = ImageStats(total_images=total_images, missing_alt=missing_alt)

        # Extract JSON-LD
        json_ld = response.xpath('//script[@type="application/ld+json"]/text()').getall()

        # Extract text content
        text_content = " ".join(soup.stripped_strings)[:5000]

        # 2. Call AI Service (Async)
        try:
            audit_result = await analyze_with_ollama(
                url=response.url,
                html=html_snippet,
                json_ld=json_ld,
                text=text_content,
                meta_tags=meta_tags,
                headers=headers,
                image_stats=image_stats
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
