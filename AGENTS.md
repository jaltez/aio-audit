# Agentic Guidelines

This project is set up to be agent-friendly.

## Environment

- Always use the `.venv` virtual environment for python commands.
- The environment includes `scrapy`, `scrapy-playwright`, `pydantic`, `openai`, `python-dotenv`, `lxml`, `pyyaml`, `streamlit`, `pandas`, and `plotly`.

## Project Structure

- `ai_seo_auditor/`: The Scrapy project root.
- `ai_seo_auditor/spiders/`: Spider definitions.
- `ai_seo_auditor/models/`: Pydantic data models (includes business-rule validators, e.g. schema_analysis score → 0 when no JSON-LD detected).
- `ai_seo_auditor/services/`: LLM integration services (flattened JSON schema, few-shot prompt, max_tokens).
- `ai_seo_auditor/config.yaml`: Audit configuration (URLs, depth, page limits, truncation, LLM retry settings).
- `dashboard.py`: Streamlit dashboard for visualizing reports.

## Development Workflow

1. Modify Pydantic models in `models/schemas.py` to change output requirements.
2. Update prompts in `services/llm_service.py` to match model changes. The LLM schema is auto-flattened from Pydantic — no need to maintain it separately.
3. Edit `config.yaml` to adjust crawl targets, limits, or LLM retry settings (`llm_timeout_seconds`, `llm_retry_attempts`, `llm_retry_base_delay`).
4. Run `cd ai_seo_auditor && scrapy crawl audit` to test.
5. Review results with `streamlit run dashboard.py` from project root.

## Key Constraints

- **Type Safety**: All LLM outputs must be validated by Pydantic. Error fallbacks also go through `PageAudit.model_validate()`.
- **Business Rules**: `SchemaScore` enforces `score == 0` when `detected_types` is empty via a `@model_validator`.
- **Resource Management**: Playwright is resource-intensive; keep concurrency low during dev.
- **HTTP Cache**: Enabled by default (1h TTL). Delete `.scrapy/httpcache/` or set `HTTPCACHE_ENABLED = False` for fresh results.
