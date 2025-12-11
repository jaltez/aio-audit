import scrapy
from scrapy_playwright.page import PageMethod
from ai_seo_auditor.services.llm_service import analyze_with_ollama
from ai_seo_auditor.models.schemas import PageAudit

class AuditSpider(scrapy.Spider):
    name = "audit"

    def start_requests(self):
        # Default start URL for testing
        urls = ["https://books.toscrape.com/"]

        # Determine if we should take URLs from arguments
        if hasattr(self, "url"):
            urls = [self.url]

        for url in urls:
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
        self.logger.info(f"Auditing {response.url}")

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
