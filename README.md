# AI-SEO Auditor

An automated tool that detects "AI-readiness" gaps in web pages using Scrapy, Playwright, and LLM analysis (Ollama).

## Features

- **Semantic Analysis**: Checks proper HTML heading hierarchy, content-title alignment, and structural SEO best practices.
- **Schema Validation**: Validates Structured Data (JSON-LD) against Schema.org types and scores completeness.
- **Content Analysis**: Evaluates whether pages provide direct, concise answers suitable for AI consumption.
- **Report Generation**: Outputs strict JSON reports quantifying compliance per-page plus an aggregate site summary.
- **Interactive Dashboard**: Streamlit-based visualizations — histograms, scatter plots, drill-downs per page.

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.ai/) running locally (or any OpenAI-compatible API).
- Node.js (required by Playwright for browser automation).

## Setup

1. **Clone the repository:**

    ```bash
    git clone <repository_url>
    cd aio-audit
    ```

2. **Create and activate a virtual environment:**

    ```bash
    # Windows
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

    # Unix/MacOS
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

4. **Pull an Ollama model:**

    ```bash
    ollama pull qwen3:8b
    ```

5. **Configuration:**

    Create a `.env` file in the **project root** (`aio-audit/`) with your LLM settings:

    ```env
    OLLAMA_BASE_URL=http://localhost:11434/v1
    OLLAMA_API_KEY=ollama
    OLLAMA_MODEL=qwen3:8b
    ```

    Edit `ai_seo_auditor/config.yaml` to set crawl targets and limits:

    ```yaml
    audit:
      start_urls:
        - "https://example.com/"
      max_depth: 2          # How many link-levels deep to follow (0 = start pages only)
      max_pages: 10         # Maximum pages to audit per session
      llm_timeout_seconds: 60
      llm_retry_attempts: 2
      llm_retry_base_delay: 1.0   # Exponential backoff base (seconds)
      html_max_chars: 8000  # Cleaned HTML truncation limit sent to LLM
      text_max_chars: 2000  # Plain-text truncation limit sent to LLM
    ```

## Usage

Run the spider:

```bash
cd ai_seo_auditor
scrapy crawl audit
```

Override settings via CLI:

```bash
scrapy crawl audit -a url=https://example.com -a max_depth=1 -a max_pages=5
```

### View Reports (Dashboard)

Start the interactive dashboard to visualize audit results:

```bash
# From the project root (aio-audit/)
streamlit run dashboard.py
```

## Report Format

Each audited page produces a JSON file in `ai_seo_auditor/reports/<domain>_<timestamp>/`. An aggregate `_site_summary.json` is also generated with average scores.

### Per-page JSON structure

```jsonc
{
  "url": "https://example.com/page",
  "meta_tags": {
    "title": "…", "description": "…", "canonical": "…",
    "og_title": "…", "og_description": "…", "og_image": "…",
    "robots": "…", "viewport": "…", "twitter_card": "…"
  },
  "headers": { "h1": ["…"], "h2": ["…"], "h3": ["…"], "h4_h6_count": 0 },
  "image_stats": { "total_images": 5, "missing_alt": 1, "empty_alt": 0 },
  "semantic_analysis": {
    "score": 75,   // 0-100
    "issues": [
      { "severity": "high|medium|low", "description": "…", "suggested_fix": "…" }
    ]
  },
  "schema_analysis": {
    "score": 0,    // 0 when no JSON-LD detected
    "detected_types": [],
    "missing_fields": []
  },
  "content_analysis": {
    "score": 60,
    "has_direct_answer": false,
    "answer_snippet": null
  }
}
```

### Site summary (`_site_summary.json`)

```jsonc
{
  "pages_audited": 10,
  "avg_semantic_score": 68.5,
  "avg_schema_score": 12.0,
  "avg_content_score": 55.3,
  "pages": [ /* per-page scores sorted by semantic_score */ ]
}
```

## Architecture

```
User → config.yaml / .env
         ↓
    AuditSpider (Scrapy + Playwright)
         ↓  extracts HTML, meta tags, headers, images, JSON-LD, text
    LLM Service (Ollama via OpenAI-compatible API)
         ↓  returns structured JSON validated by Pydantic
    JsonReportPipeline
         ↓  writes per-page .json + _site_summary.json
    Streamlit Dashboard (reads reports/)
```

- **Scrapy**: Crawling framework with depth and page-count limits.
- **Playwright**: Headless Chromium for rendering JavaScript-heavy pages.
- **Pydantic**: Strict validation of all LLM outputs — guarantees schema compliance.
- **Ollama**: Local LLM inference via OpenAI-compatible `/v1/chat/completions` API.
- **Streamlit**: Interactive, cacheable dashboard for report visualization.

## Important Notes

- **`robots.txt` is obeyed** — URLs blocked by the target site's `robots.txt` will be silently skipped. Set `ROBOTSTXT_OBEY = False` in `ai_seo_auditor/ai_seo_auditor/settings.py` if you need to override (respect site policies).
- **HTTP caching is enabled** — responses are cached for 1 hour in `.scrapy/httpcache/` to speed up development re-runs. For fresh production audits, set `HTTPCACHE_ENABLED = False` in `settings.py`.
- **Reports are git-ignored** — the `ai_seo_auditor/reports/` directory is in `.gitignore`.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Connection refused` to Ollama | Ensure Ollama is running (`ollama serve`) and `OLLAMA_BASE_URL` is correct in `.env`. |
| Spider finishes with 0 pages | Check that `robots.txt` isn't blocking your target. Add `-s ROBOTSTXT_OBEY=False` to test. |
| `playwright._impl._errors.Error` | Run `playwright install chromium` to install browser binaries. |
| LLM returns invalid JSON | Increase `llm_timeout_seconds` or try a larger model. The prompt is optimized for 8B+ models. |
| Stale results on re-crawl | Delete `.scrapy/httpcache/` or set `HTTPCACHE_ENABLED = False` in `settings.py`. |
| Dashboard shows no reports | Run `streamlit run dashboard.py` from the **project root** (`aio-audit/`), not from `ai_seo_auditor/`. |
