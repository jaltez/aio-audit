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

1.  **Clone the repository:**

    ```bash
    git clone <repository_url>
    cd aio-audit
    ```

2.  **Create and activate a virtual environment:**

    ```bash
    # Windows
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

    # Unix/MacOS
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**

    ```bash
    pip install scrapy scrapy-playwright pydantic openai python-dotenv
    playwright install chromium
    ```

4.  **Configuration:**
    Create a `.env` file in the `ai_seo_auditor` directory (or root) based on your LLM setup.
    ```env
    OLLAMA_BASE_URL=http://localhost:11434/v1
    OLLAMA_API_KEY=ollama
    OLLAMA_MODEL=qwen3:8b # or any other model you have pulled in Ollama
    ```

## Usage

Run the spider:

```bash
cd ai_seo_auditor
scrapy crawl audit
```

## Architecture

- **Scrapy**: Crawling framework.
- **Playwright**: Headless browser for rendering JS.
- **Pydantic**: Data validation.
- **Ollama**: LLM inference.
