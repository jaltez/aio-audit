# Agentic Guidelines

This project is set up to be agent-friendly.

## Environment

- Always usage the `.venv` virtual environment for python commands.
- The environment includes `scrapy`, `scrapy-playwright`, `pydantic`, and `openai`.

## Project Structure

- `ai_seo_auditor/`: The Scrapy project root.
- `ai_seo_auditor/spiders/`: Spider definitions.
- `ai_seo_auditor/models/`: Pydantic data models.
- `ai_seo_auditor/services/`: LLM integration services.

## Development Workflow

1.  Modify Pydantic models in `models/schemas.py` to change output requirements.
2.  Update prompts in `services/llm_service.py` to match model changes.
3.  Run `scrapy crawl audit` to test.

## Key Constraints

- **Type Safety**: All LLM outputs must be validated by Pydantic.
- **Resource Management**: Playwright is resource-intensive; keep concurrency low during dev.
