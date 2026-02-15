# Agentic Guidelines

This project is set up to be agent-friendly.

## Environment

- Always use the `.venv` virtual environment for python commands.
- The environment includes `scrapy`, `scrapy-playwright`, `pydantic`, `openai`, `python-dotenv`, `lxml`, `pyyaml`, `streamlit`, `pandas`, and `plotly`.

## Project Structure

- `ai_seo_auditor/`: The Scrapy project root.
- `ai_seo_auditor/spiders/`: Spider definitions.
- `ai_seo_auditor/models/`: Pydantic data models.
- `ai_seo_auditor/services/`: LLM integration services.
- `ai_seo_auditor/config.yaml`: Audit configuration (URLs, depth, page limits, truncation).
- `dashboard.py`: Streamlit dashboard for visualizing reports.

## Development Workflow

1. Modify Pydantic models in `models/schemas.py` to change output requirements.
2. Update prompts in `services/llm_service.py` to match model changes.
3. Edit `config.yaml` to adjust crawl targets or limits.
4. Run `cd ai_seo_auditor && scrapy crawl audit` to test.
5. Review results with `streamlit run dashboard.py` from project root.

## Key Constraints

- **Type Safety**: All LLM outputs must be validated by Pydantic.
- **Resource Management**: Playwright is resource-intensive; keep concurrency low during dev.
