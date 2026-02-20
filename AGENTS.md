# Agentic Guidelines

This project is set up to be agent-friendly.

## Environment

- Always use the `.venv` virtual environment for python commands.
- The environment includes `scrapy`, `scrapy-playwright`, `pydantic`, `openai`, `python-dotenv`, `lxml`, `pyyaml`, `streamlit`, `pandas`, and `plotly`.

## Project Structure

- `ai_seo_auditor/`: Scrapy project root/config container.
- `ai_seo_auditor/spiders/`: Spider definitions.
- `ai_seo_auditor/models/`: Pydantic data models (includes business-rule validators and auto-scoring `@model_validator`s).
- `ai_seo_auditor/services/`: LLM integration services (flattened JSON schema, few-shot prompt, max_tokens).
- `ai_seo_auditor/config.yaml`: Audit configuration (URLs, depth, page limits, truncation, LLM retry settings, score weights).
- `dashboard.py`: Streamlit dashboard for visualizing reports.
- `reports/`: Root-level report output directory.

## Audit Dimensions (8 total)

The audit scores pages across 8 dimensions:

| Dimension | Source | Model |
|-----------|--------|-------|
| `onpage_seo` | Spider only (deterministic) | `OnPageSeoChecklist` — 11 binary checks totalling 100 pts (title, meta desc, H1, heading hierarchy, images alt, OG tags, canonical, lang attr, robots, keyword presence, internal links) |
| `schema_analysis` | LLM | `SchemaScore` — JSON-LD quality (score=0 when `detected_types` is empty) |
| `content_analysis` | LLM | `ContentScore` — answers_user_intent, content_uniqueness_note, issues |
| `link_analysis` | Spider counts + LLM score | `LinkAnalysis` — internal/external links, anchor quality, generic link text count |
| `performance` | Spider only (deterministic) | `PerformanceMetrics` — TTFB, FCP, DOMContentLoaded, page size, resource count (auto-scored via Web Vitals thresholds, 25% each) |
| `readability` | Spider only (deterministic) | `ReadabilityAnalysis` — Flesch-Kincaid Grade Level, Flesch Reading Ease, thin-content flag (auto-scored) |
| `security` | Spider only (deterministic) | `SecurityCheck` — HTTPS, headers (auto-scored) |
| `accessibility` | Spider structure + LLM | `AccessibilityAnalysis` — blended: 50% deterministic checklist (lang attr, alt coverage, generic links, heading structure, tabindex, ARIA, skip-nav, document title) + 50% LLM qualitative score |

Additional spider-computed: `canonical_analysis` (CanonicalAnalysis — canonical match, redirects, hreflang). Not included in weighted average.

Overall score = weighted average of all 8 dimensions (weights in `config.yaml`).
Letter grade: A (≥90), B (≥80), C (≥70), D (≥60), F (<60).
Color thresholds are Lighthouse-aligned: ≥90 green, 50–89 orange, <50 red.

## LLM vs Spider Split

- **Fully deterministic (spider-only)**: `onpage_seo`, `performance`, `readability`, `security`, `canonical_analysis`.
- **LLM-scored (4 dimensions)**: `schema_analysis`, `content_analysis`, `link_analysis` (score + issues), `accessibility` (llm_score + issues).
- The LLM receives spider-extracted context (meta tags, headers, body text, link counts, accessibility stats) and returns scores + issues for the 4 LLM dimensions only.

## Development Workflow

1. Modify Pydantic models in `ai_seo_auditor/models/schemas.py` to change output requirements.
2. Update prompts in `ai_seo_auditor/services/llm_service.py` to match model changes. The LLM schema is auto-flattened from Pydantic — no need to maintain it separately.
3. Edit `config.yaml` to adjust crawl targets, limits, LLM retry settings, or `score_weights`.
4. Run `uv run scrapy crawl audit` from project root to test.
5. Review results with `uv run streamlit run dashboard.py` from project root.
6. For repeated local runs after initial sync, prefer `uv run --no-sync scrapy crawl audit` and `uv run --no-sync streamlit run dashboard.py`.

## Key Constraints

- **Type Safety**: All LLM outputs must be validated by Pydantic. Error fallbacks also go through `PageAudit.model_validate()`.
- **Business Rules**: `SchemaScore` enforces `score == 0` when `detected_types` is empty via a `@model_validator`. `PerformanceMetrics`, `SecurityCheck`, `ReadabilityAnalysis`, `OnPageSeoChecklist`, and `CanonicalAnalysis` auto-compute scores via `@model_validator`. `AccessibilityAnalysis` computes a blended score (50% deterministic + 50% LLM).
- **LLM Prompt Design**: Prompts include severity rubric (high/medium/low), per-dimension checklists, and explicit instructions. LLM produces only `llm_score` for accessibility (not the final `score`).
- **Audit Status**: Each page gets `audit_status`: `"complete"` (LLM succeeded), `"partial"` (LLM failed, spider data only), or `"failed"` (spider also failed). Failed pages are excluded from site averages.
- **Resource Management**: Playwright is resource-intensive; keep concurrency low during dev.
- **HTTP Cache**: Enabled by default (1h TTL). Delete `.scrapy/httpcache/` or set `HTTPCACHE_ENABLED = False` for fresh results.
- **Report Format**: Breaking changes to PageAudit require a re-crawl. The dashboard includes backward-compat migration for old-format reports (maps `semantic_analysis` → `onpage_seo`, `response_time_ms` → `ttfb_ms`).
- **Playwright Timing**: The spider injects JavaScript via `page.evaluate()` to extract `navigationStart`, TTFB, FCP, and DOMContentLoaded from the Performance API. Falls back to Scrapy `download_latency` when Playwright data is unavailable.

## Dashboard Features

- **Site-wide grade**: Letter grade (A–F) hero badge with radar chart of all 8 dimensions.
- **Lighthouse colors**: Score cards use ≥90 green, 50–89 orange, <50 red.
- **Score distributions**: Box plots and configurable scatter plots.
- **Issue aggregation**: Top issues across all pages with severity counts.
- **Filtering**: URL search, score range slider, severity filter.
- **Page drill-down**: 8 tabs (Overview, On-Page SEO, Schema, Content/Readability, Links, Performance, Security, Accessibility/Canonical).
- **On-Page SEO tab**: Shows all 11 checklist items with pass/fail status and point weights.
- **Performance tab**: TTFB/FCP/DCL gauges with Web Vitals threshold reference table.
- **Readability tab**: Flesch-Kincaid metrics (FRE, FK Grade, avg sentence length, thin content flag).
- **Accessibility tab**: Blended score breakdown (deterministic checklist + LLM qualitative score).
- **Export**: CSV and full JSON download from the sidebar.
- **Dark theme**: Custom CSS with color-coded score cards.
- **Backward compat**: Old reports (pre-overhaul) are auto-migrated on load.
