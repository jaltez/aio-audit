# AI-SEO Auditor

An automated tool that detects "AI-readiness" gaps in web pages using Scrapy, Playwright, and LLM analysis (Ollama).

## Features

- **Semantic Analysis**: Checks proper HTML structure and hierarchy.
- **Schema Validation**: Validates Structured Data (JSON-LD) against Schema.org types.
- **Content Analysis**: Checks for direct answer availability and concise content.
- **Report Generation**: Outputs strict JSON reports quantifying compliance.

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.ai/) running locally (or compatible API).
- Node.js (for Playwright internal dependencies).

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
      max_depth: 2
      max_pages: 10
      html_max_chars: 8000
      text_max_chars: 2000
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
# From the project root
streamlit run dashboard.py
```

## Architecture

- **Scrapy**: Crawling framework.
- **Playwright**: Headless browser for rendering JS.
- **Pydantic**: Data validation for all LLM outputs.
- **Ollama**: LLM inference (OpenAI-compatible API).
- **Streamlit**: Interactive dashboard for report visualization.
