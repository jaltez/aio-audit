import asyncio
import json
import time

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
from ai_seo_auditor.services.llm_service import analyze_with_llm
from ai_seo_auditor.models.schemas import (
    MetaTags, HeaderStructure, ImageStats, PageAudit,
    LinkAnalysis, PerformanceMetrics, ReadabilityAnalysis,
    SecurityCheck, AccessibilityAnalysis, CanonicalAnalysis,
)


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
        self._pages_lock = asyncio.Lock()
        self._llm_semaphore = asyncio.Semaphore(1)  # serialize LLM calls
        self._last_llm_call: float = 0.0  # monotonic timestamp of last LLM call

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
        async with self._pages_lock:
            if self.pages_analyzed >= self.max_pages:
                self.logger.info(f"Max pages limit ({self.max_pages}) reached. Stopping audit for {response.url} and future pages.")
                return
            self.pages_analyzed += 1
            current_page = self.pages_analyzed

        # Skip non-HTML responses (images, PDFs, etc.)
        content_type = response.headers.get("Content-Type", b"").decode("utf-8", errors="ignore")
        if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
            self.logger.info(f"Skipping non-HTML response ({content_type}): {response.url}")
            return

        self.logger.info(f"Auditing {response.url} (Page {current_page}/{self.max_pages})")

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
            og_description=response.xpath('//meta[@property="og:description"]/@content').get(),
            robots=response.xpath('//meta[@name="robots"]/@content').get(),
            viewport=response.xpath('//meta[@name="viewport"]/@content').get(),
            og_image=response.xpath('//meta[@property="og:image"]/@content').get(),
            twitter_card=response.xpath('//meta[@name="twitter:card"]/@content').get(),
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

        # Extract Image Stats — distinguish truly missing alt from empty alt=""
        images = response.xpath('//img')
        total_images = len(images)
        missing_alt = len(response.xpath('//img[not(@alt)]'))
        empty_alt = len(response.xpath('//img[@alt=""]'))
        image_stats = ImageStats(
            total_images=total_images, missing_alt=missing_alt, empty_alt=empty_alt
        )

        # Extract JSON-LD — parse raw strings into dicts so the LLM sees real JSON
        raw_json_ld = response.xpath('//script[@type="application/ld+json"]/text()').getall()
        json_ld: list[dict] = []
        for raw in raw_json_ld:
            try:
                json_ld.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                self.logger.warning(f"Invalid JSON-LD on {response.url}: {raw[:120]}")

        # Extract text content
        text_content = " ".join(text.strip() for text in body.itertext() if text and text.strip())
        text_content = text_content[:self.text_max_chars]

        # -------------------------------------------------------------------
        # NEW: Link Analysis
        # -------------------------------------------------------------------
        all_links = response.xpath('//a[@href]')
        page_hostname = urlparse(response.url).hostname or ""
        internal_count = 0
        external_count = 0
        nofollow_count = 0
        for a in all_links:
            href = a.attrib.get("href", "")
            rel = (a.attrib.get("rel") or "").lower()
            if "nofollow" in rel:
                nofollow_count += 1
            parsed = urlparse(href)
            link_host = parsed.hostname
            if link_host is None or link_host == page_hostname:
                internal_count += 1
            else:
                external_count += 1

        link_analysis = LinkAnalysis(
            score=0,  # LLM will override
            internal_links=internal_count,
            external_links=external_count,
            nofollow_count=nofollow_count,
            broken_links=[],  # populated later if broken-link checking enabled
        )

        # -------------------------------------------------------------------
        # NEW: Performance Metrics
        # -------------------------------------------------------------------
        download_latency = response.meta.get("download_latency", 0)
        response_time_ms = int(download_latency * 1000)
        page_size_bytes = len(response.body)
        script_count = len(response.xpath('//script[@src]'))
        stylesheet_count = len(response.xpath('//link[@rel="stylesheet"]'))
        resource_count = script_count + stylesheet_count + total_images

        performance = PerformanceMetrics(
            score=0,  # auto-computed by model_validator
            response_time_ms=response_time_ms,
            page_size_bytes=page_size_bytes,
            resource_count=resource_count,
        )

        # -------------------------------------------------------------------
        # NEW: Readability data
        # -------------------------------------------------------------------
        word_count = len(text_content.split()) if text_content else 0

        readability = ReadabilityAnalysis(
            score=0,  # LLM will override
            word_count=word_count,
        )

        # -------------------------------------------------------------------
        # NEW: Security headers
        # -------------------------------------------------------------------
        is_https = response.url.startswith("https")
        has_hsts = bool(response.headers.get("Strict-Transport-Security"))
        has_csp = bool(response.headers.get("Content-Security-Policy"))
        has_x_ct = bool(response.headers.get("X-Content-Type-Options"))

        # Detect mixed content — http:// resources referenced in the HTML
        mixed: list[str] = []
        if is_https:
            for src_attr in ('src', 'href'):
                for el in cleaned_root.xpath(f'//*[@{src_attr}]'):
                    val = el.get(src_attr, '')
                    if val.startswith('http://'):
                        mixed.append(val)

        security = SecurityCheck(
            score=0,  # auto-computed by model_validator
            is_https=is_https,
            has_hsts=has_hsts,
            has_csp=has_csp,
            has_x_content_type=has_x_ct,
            mixed_content_urls=mixed[:20],  # cap to avoid huge lists
        )

        # -------------------------------------------------------------------
        # NEW: Accessibility basics
        # -------------------------------------------------------------------
        has_skip_nav = bool(
            response.xpath('//a[contains(translate(@class,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"skip")]')
            or response.xpath('//a[starts-with(@href,"#main")]')
            or response.xpath('//a[starts-with(@href,"#content")]')
        )
        aria_landmarks = len(response.xpath(
            '//*[@role="banner" or @role="navigation" or @role="main" '
            'or @role="contentinfo" or @role="complementary" or @role="search"]'
        ))
        # Inputs without associated labels
        all_inputs = response.xpath('//input[not(@type="hidden")]')
        labeled_by_for = response.xpath('//label/@for').getall()
        labels_missing = 0
        for inp in all_inputs:
            inp_id = inp.attrib.get("id", "")
            has_aria = inp.attrib.get("aria-label") or inp.attrib.get("aria-labelledby")
            has_label_for = inp_id and inp_id in labeled_by_for
            # Check if input is wrapped in a <label>
            has_wrapping_label = bool(inp.xpath('ancestor::label'))
            if not has_aria and not has_label_for and not has_wrapping_label:
                labels_missing += 1

        accessibility = AccessibilityAnalysis(
            score=0,  # LLM will override
            has_skip_nav=has_skip_nav,
            aria_landmark_count=aria_landmarks,
            form_labels_missing=labels_missing,
        )

        # -------------------------------------------------------------------
        # NEW: Canonical / redirect analysis
        # -------------------------------------------------------------------
        canonical_url = meta_tags.canonical
        redirect_urls = response.meta.get("redirect_urls", [])
        matches_actual = (
            canonical_url is not None
            and canonical_url.rstrip("/") == response.url.rstrip("/")
        )
        has_hreflang = bool(response.xpath('//link[@rel="alternate" and @hreflang]'))

        canonical_analysis = CanonicalAnalysis(
            score=0,  # auto-computed by model_validator
            canonical_url=canonical_url,
            matches_actual_url=matches_actual if canonical_url else True,
            redirect_chain=[str(u) for u in redirect_urls],
            has_hreflang=has_hreflang,
        )

        # 2. Call AI Service (Async)
        audit_config = self.config.get("audit", {})
        timeout_seconds = float(audit_config.get("llm_timeout_seconds", 60))
        retry_attempts = int(audit_config.get("llm_retry_attempts", 2))
        retry_base_delay = float(audit_config.get("llm_retry_base_delay", 1.0))
        rate_limit_delay = float(audit_config.get("llm_rate_limit_delay", 0))

        # Serialize LLM calls: only one runs at a time, with rate-limit padding
        async with self._llm_semaphore:
            if rate_limit_delay > 0:
                now = time.monotonic()
                wait = self._last_llm_call + rate_limit_delay - now
                if wait > 0:
                    self.logger.debug(f"Rate-limit: sleeping {wait:.2f}s before LLM call")
                    await asyncio.sleep(wait)

            try:
                self._last_llm_call = time.monotonic()
                audit_result = await analyze_with_llm(
                    url=response.url,
                    html=html_snippet,
                    json_ld=json_ld,
                    text=text_content,
                    meta_tags=meta_tags,
                    headers=headers,
                    image_stats=image_stats,
                    link_analysis=link_analysis,
                    performance=performance,
                    readability=readability,
                    security=security,
                    accessibility=accessibility,
                    canonical_analysis=canonical_analysis,
                    timeout_seconds=timeout_seconds,
                    retry_attempts=retry_attempts,
                    retry_base_delay=retry_base_delay,
                    logger=self.logger,
                )
            except Exception as e:
                audit_result = None
                llm_error = e
            else:
                llm_error = None

        if llm_error is not None:
            self.logger.error(f"Error auditing {response.url}: {llm_error}")
            # Yield a validated error report so schema compliance is guaranteed
            error_report = PageAudit.model_validate({
                "url": response.url,
                "meta_tags": meta_tags.model_dump(),
                "headers": headers.model_dump(),
                "image_stats": image_stats.model_dump(),
                "semantic_analysis": {
                    "score": 0,
                    "issues": [{"severity": "high", "description": f"Audit failed: {llm_error}", "suggested_fix": "Retry or check logs."}],
                },
                "schema_analysis": {"score": 0, "detected_types": [], "missing_fields": []},
                "content_analysis": {"score": 0, "has_direct_answer": False, "answer_snippet": None},
                "link_analysis": link_analysis.model_dump(),
                "performance": performance.model_dump(),
                "readability": readability.model_dump(),
                "security": security.model_dump(),
                "accessibility": {"score": 0, "has_skip_nav": accessibility.has_skip_nav, "aria_landmark_count": accessibility.aria_landmark_count, "form_labels_missing": accessibility.form_labels_missing, "issues": []},
                "canonical_analysis": canonical_analysis.model_dump(),
            })
            yield error_report.model_dump()
        else:
            # 3. Yield the validated Pydantic model
            yield audit_result.model_dump()

        # 4. Crawl: Extract and follow links if depth allows
        current_depth = response.meta.get('depth', 0)
        if current_depth < self.max_depth and self.pages_analyzed < self.max_pages:
            le = LinkExtractor(allow_domains=self.allowed_domains)
            links = le.extract_links(response)

            for link in links:
                if self.pages_analyzed >= self.max_pages:
                    break
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
