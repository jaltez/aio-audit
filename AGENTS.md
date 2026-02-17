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
- `ai_seo_auditor/config.yaml`: Audit configuration (URLs, depth, page limits, truncation, LLM retry settings, score weights).
- `dashboard.py`: Streamlit dashboard for visualizing reports.

## Audit Dimensions (8 total)

The audit scores pages across 8 dimensions:

| Dimension | Source | Model |
|-----------|--------|-------|
| `semantic_analysis` | LLM | `SemanticScore` — header hierarchy, on-page SEO |
| `schema_analysis` | LLM | `SchemaScore` — JSON-LD quality (score=0 when none) |
| `content_analysis` | LLM | `ContentScore` — direct-answer, conciseness |
| `link_analysis` | Spider counts + LLM score | `LinkAnalysis` — internal/external links, anchor quality |
| `performance` | Spider only | `PerformanceMetrics` — response time, page size (auto-scored) |
| `readability` | Spider word-count + LLM | `ReadabilityAnalysis` — reading level, keyword density |
| `security` | Spider only | `SecurityCheck` — HTTPS, headers (auto-scored) |
| `accessibility` | Spider structure + LLM | `AccessibilityAnalysis` — ARIA, skip-nav, form labels |

Additional spider-computed: `canonical_analysis` (CanonicalAnalysis — canonical match, redirects, hreflang).

Overall score = weighted average of all 8 dimensions (weights in `config.yaml`).
Letter grade: A (≥90), B (≥80), C (≥70), D (≥60), F (<60).

## Development Workflow

1. Modify Pydantic models in `models/schemas.py` to change output requirements.
2. Update prompts in `services/llm_service.py` to match model changes. The LLM schema is auto-flattened from Pydantic — no need to maintain it separately.
3. Edit `config.yaml` to adjust crawl targets, limits, LLM retry settings, or `score_weights`.
4. Run `cd ai_seo_auditor && scrapy crawl audit` to test.
5. Review results with `streamlit run dashboard.py` from project root.

## Key Constraints

- **Type Safety**: All LLM outputs must be validated by Pydantic. Error fallbacks also go through `PageAudit.model_validate()`.
- **Business Rules**: `SchemaScore` enforces `score == 0` when `detected_types` is empty via a `@model_validator`. `PerformanceMetrics`, `SecurityCheck`, and `CanonicalAnalysis` auto-compute scores via `@model_validator`.
- **LLM vs Spider split**: Performance, security, and canonical are fully spider-computed (deterministic). Link analysis, readability, and accessibility use spider data as context but LLM provides the score.
- **Resource Management**: Playwright is resource-intensive; keep concurrency low during dev.
- **HTTP Cache**: Enabled by default (1h TTL). Delete `.scrapy/httpcache/` or set `HTTPCACHE_ENABLED = False` for fresh results.
- **Report Format**: Breaking changes to PageAudit require a re-crawl. Old reports are not backward-compatible.

## Dashboard Features

- **Site-wide grade**: Letter grade (A–F) hero badge with radar chart of all 8 dimensions.
- **Score distributions**: Box plots and configurable scatter plots.
- **Issue aggregation**: Top issues across all pages with severity counts.
- **Filtering**: URL search, score range slider, severity filter.
- **Page drill-down**: 8 tabs (Overview, Semantic, Schema, Content/Readability, Links, Performance, Security, Accessibility/Canonical).
- **Export**: CSV and full JSON download from the sidebar.
- **Dark theme**: Custom CSS with color-coded score cards.
