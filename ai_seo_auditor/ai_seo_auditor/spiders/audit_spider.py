import scrapy
import yaml
from lxml import etree
from lxml.html import fromstring as html_fromstring
from pathlib import Path
from scrapy.http import TextResponse
from scrapy.linkextractors import LinkExtractor
from scrapy_playwright.page import PageMethod
from typing import Any, AsyncGenerator
from urllib.parse import urlparse
from ai_seo_auditor.services.llm_service import analyze_with_ollama
from ai_seo_auditor.models.schemas import MetaTags, HeaderStructure, ImageStats


class AuditSpider(scrapy.Spider):
    name = "audit"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Load config from yaml file located at project root
        # File structure: project_root/ai_seo_auditor/spiders/audit_spider.py
        # Config location: project_root/config.yaml
        config_path = Path(__file__).resolve().parents[2] / 'config.yaml'
        self.config: dict = {}
        if config_path.exists():
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f) or {}
        else:
            self.logger.warning(f"Config file not found at {config_path}. Using defaults.")

        audit_config = self.config.get('audit', {})

        # Validate key config values
        try:
            self.max_depth: int = int(kwargs.get('max_depth', audit_config.get('max_depth', 2)))
            self.max_pages: int = int(kwargs.get('max_pages', audit_config.get('max_pages', 10)))
            self.html_max_chars: int = int(audit_config.get('html_max_chars', 8000))
            self.text_max_chars: int = int(audit_config.get('text_max_chars', 2000))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid config value (must be integers): {e}") from e

        if self.max_depth < 0 or self.max_pages < 1:
            raise ValueError(f"max_depth must be >= 0 and max_pages >= 1, got {self.max_depth}, {self.max_pages}")

        self.pages_analyzed: int = 0

        # Initialize start_urls
        self.start_urls = audit_config.get('start_urls', ["https://books.toscrape.com/"])
        if not isinstance(self.start_urls, list) or not self.start_urls:
            raise ValueError("start_urls must be a non-empty list of URLs")

        if kwargs.get("url"):
            self.start_urls = [kwargs["url"]]

        # Set allowed_domains dynamically based on input URLs, normalizing ports
        self.allowed_domains = list({urlparse(url).hostname for url in self.start_urls if urlparse(url).hostname})

    def start_requests(self) -> Any:
        self.logger.info(f"Starting audit with max_depth={self.max_depth}, max_pages={self.max_pages}")

        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_load_state", "domcontentloaded")
                    ],
                }
            )

    async def parse(self, response: TextResponse) -> AsyncGenerator[dict, None]:
        if self.pages_analyzed >= self.max_pages:
            self.logger.info(f"Max pages limit ({self.max_pages}) reached. Stopping audit for {response.url} and future pages.")
            return

        # Skip non-HTML responses (images, PDFs, etc.)
        content_type = response.headers.get("Content-Type", b"").decode("utf-8", errors="ignore")
        if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
            self.logger.info(f"Skipping non-HTML response ({content_type}): {response.url}")
            return

        self.pages_analyzed += 1
        self.logger.info(f"Auditing {response.url} (Page {self.pages_analyzed}/{self.max_pages})")

        # 1. Prepare Data
        # Parse a fresh lxml tree from the response body (avoids expensive deepcopy)
        try:
            cleaned_root = html_fromstring(response.text)
        except Exception:
            try:
                cleaned_root = html_fromstring(response.body)
            except Exception as parse_err:
                self.logger.error(f"Failed to parse HTML for {response.url}: {parse_err}")
                return

        for element in cleaned_root.xpath("//script | //style | //svg | //noscript | //iframe"):
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)

        body_nodes = cleaned_root.xpath("//body")
        body = body_nodes[0] if body_nodes else cleaned_root
        html_snippet = etree.tostring(body, encoding="unicode", method="html")
        # Single truncation point — no further truncation in llm_service
        html_snippet = html_snippet[:self.html_max_chars]

        # Extract Meta Tags (whitespace stripping handled by Pydantic validator)
        meta_tags = MetaTags(
            title=response.xpath('//title/text()').get(),
            description=response.xpath('//meta[@name="description"]/@content').get(),
            canonical=response.xpath('//link[@rel="canonical"]/@href').get(),
            og_title=response.xpath('//meta[@property="og:title"]/@content').get(),
            og_description=response.xpath('//meta[@property="og:description"]/@content').get()
        )

        # Extract Header Structure (use //text() to capture nested text like <h1><a>Title</a></h1>)
        def extract_header_texts(tag: str) -> list[str]:
            return [
                " ".join(h.xpath('.//text()').getall()).strip()
                for h in response.xpath(f'//{tag}')
            ]

        headers = HeaderStructure(
            h1=extract_header_texts('h1'),
            h2=extract_header_texts('h2'),
            h3=extract_header_texts('h3'),
            h4_h6_count=len(response.xpath('//h4 | //h5 | //h6'))
        )

        # Extract Image Stats
        images = response.xpath('//img')
        total_images = len(images)
        missing_alt = len(response.xpath('//img[not(@alt) or @alt=""]'))
        image_stats = ImageStats(total_images=total_images, missing_alt=missing_alt)

        # Extract JSON-LD
        json_ld = response.xpath('//script[@type="application/ld+json"]/text()').getall()

        # Extract text content
        text_content = " ".join(text.strip() for text in body.itertext() if text and text.strip())
        text_content = text_content[:self.text_max_chars]

        # 2. Call AI Service (Async)
        audit_config = self.config.get("audit", {})
        timeout_seconds = float(audit_config.get("llm_timeout_seconds", 60))
        retry_attempts = int(audit_config.get("llm_retry_attempts", 2))
        try:
            audit_result = await analyze_with_ollama(
                url=response.url,
                html=html_snippet,
                json_ld=json_ld,
                text=text_content,
                meta_tags=meta_tags,
                headers=headers,
                image_stats=image_stats,
                timeout_seconds=timeout_seconds,
                retry_attempts=retry_attempts,
                logger=self.logger,
            )

            # 3. Yield the validated Pydantic model
            # We convert to dict for Scrapy pipeline compatibility
            yield audit_result.model_dump()

        except Exception as e:
            self.logger.error(f"Error auditing {response.url}: {e}")
            # Yield a minimal error report so the failure is recorded
            yield {
                "url": response.url,
                "meta_tags": meta_tags.model_dump(),
                "headers": headers.model_dump(),
                "image_stats": image_stats.model_dump(),
                "semantic_analysis": {
                    "score": 0,
                    "issues": [{"severity": "high", "description": f"Audit failed: {e}", "suggested_fix": "Retry or check logs."}],
                },
                "schema_analysis": {"score": 0, "detected_types": [], "missing_fields": []},
                "content_analysis": {"score": 0, "has_direct_answer": False, "answer_snippet": None},
            }

        # 4. Crawl: Extract and follow links if depth allows
        current_depth = response.meta.get('depth', 0)
        if current_depth < self.max_depth and self.pages_analyzed < self.max_pages:
            le = LinkExtractor(allow_domains=self.allowed_domains)
            links = le.extract_links(response)

            for link in links:
                yield scrapy.Request(
                    link.url,
                    callback=self.parse,
                    meta={
                        "playwright": True,
                        "playwright_page_methods": [
                            PageMethod("wait_for_load_state", "domcontentloaded")
                        ],
                    }
                )
