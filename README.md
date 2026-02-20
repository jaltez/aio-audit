# AI SEO Auditor

Automated SEO and AI-readiness auditing with Scrapy + Playwright + LLM scoring, plus a Streamlit dashboard.

## What it does

- Crawls pages and extracts deterministic technical signals.
- Uses an LLM for qualitative scoring where needed.
- Produces per-page JSON reports and a site summary.
- Visualizes results in a dashboard with filtering and drill-downs.

## Prerequisites

- Python 3.12+
- `uv` installed
- Node.js (required by Playwright)

## Project routes (root-first)

- Crawl config: `ai_seo_auditor/config.yaml`
- Scrapy project code: `ai_seo_auditor/`
- Dashboard entrypoint: `dashboard.py`
- Reports output (default): `reports/`

## Setup (from repository root)

1. Sync dependencies:

```bash
uv sync
```

2. Install Playwright Chromium:

```bash
uv run playwright install chromium
```

3. Create `.env` in project root:

```env
# Provider toggle: zai | ollama
LLM_PROVIDER=zai

# ZAI (default provider)
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
ZAI_MODEL=glm-4.7-flash
ZAI_API_KEY=

# Ollama (optional)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_MODEL=qwen3:8b
```

4. Edit crawl settings in `ai_seo_auditor/config.yaml`.

## Usage (from repository root)

Run a crawl:

```bash
uv run scrapy crawl audit
```

Run with overrides:

```bash
uv run scrapy crawl audit -a url=https://example.com -a max_depth=1 -a max_pages=5
```

Open dashboard:

```bash
uv run streamlit run dashboard.py
```

Fast path after initial setup (skips sync checks):

```bash
uv run --no-sync scrapy crawl audit
uv run --no-sync streamlit run dashboard.py
```

## Cross-platform notes

The `uv` commands above are identical on PowerShell, CMD, macOS, and Linux shells.

## Output

- Per-page reports: `reports/<domain>_<timestamp>/*.json`
- Site summary: `reports/<domain>_<timestamp>/_site_summary.json`

## Troubleshooting

- `playwright` errors: run `uv run playwright install chromium`
- LLM auth/provider issues: verify `.env` values and `LLM_PROVIDER`
- Empty crawl: check `robots.txt` behavior or your `start_urls`
- Dashboard can’t find data: run a crawl first and verify files under `reports/`
