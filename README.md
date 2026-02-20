# AI SEO Auditor

Automated SEO and AI-readiness auditing with Scrapy + Playwright + LLM scoring, plus a custom React + FastAPI command center.

## What it does

- Crawls pages and extracts deterministic technical signals.
- Uses an LLM for qualitative scoring where needed.
- Produces per-page JSON reports and a site summary.
- Serves reports through a FastAPI API.
- Visualizes results with a React command center.

## Prerequisites

- Python 3.12+
- `uv` installed
- Node.js (required by Playwright)

## Project routes (root-first)

- Crawl config: `ai_seo_auditor/config.yaml`
- Scrapy project code: `ai_seo_auditor/`
- API backend: `backend/main.py`
- Frontend app: `frontend/`
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

Run API backend:

```bash
uv run uvicorn backend.main:app --reload
```

Run frontend:

```bash
cd frontend
npm install
npm run dev
```

Run both with one command:

```bash
uv run python run_dev.py
```

The frontend defaults to `http://127.0.0.1:5173` and proxies `/api` to `http://127.0.0.1:8000`.

## API Endpoints

- `GET /api/sessions`
- `GET /api/sessions/{session_id}/summary`
- `GET /api/sessions/{session_id}/pages`
- `GET /api/sessions/{session_id}/pages/{page_id}`
- `GET /api/sessions/{session_id}/exports.csv`
- `GET /api/sessions/{session_id}/exports.json`

## Legacy Streamlit

The old Streamlit dashboard is still present at `dashboard.py` for reference, but the default UI path is now API + React.

## Output

- Per-page reports: `reports/<domain>_<timestamp>/*.json`
- Site summary: `reports/<domain>_<timestamp>/_site_summary.json`

## Troubleshooting

- `playwright` errors: run `uv run playwright install chromium`
- LLM auth/provider issues: verify `.env` values and `LLM_PROVIDER`
- Empty crawl: check `robots.txt` behavior or your `start_urls`
- Backend can’t find data: run a crawl first and verify files under `reports/`
