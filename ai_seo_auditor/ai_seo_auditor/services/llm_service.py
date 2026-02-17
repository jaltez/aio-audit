import asyncio
import copy
import json
import logging
import os
from typing import Any, Optional

import openai
from dotenv import load_dotenv
from openai import AsyncOpenAI

from ai_seo_auditor.models.schemas import (
    PageAudit, MetaTags, HeaderStructure, ImageStats,
    LinkAnalysis, PerformanceMetrics, ReadabilityAnalysis,
    SecurityCheck, AccessibilityAnalysis, CanonicalAnalysis,
)

# ---------------------------------------------------------------------------
# Environment / defaults
# ---------------------------------------------------------------------------
load_dotenv()

# Toggle between providers by setting LLM_PROVIDER=zai or LLM_PROVIDER=ollama
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "zai").lower()

_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key":  os.getenv("OLLAMA_API_KEY", "ollama"),
        "model":    os.getenv("OLLAMA_MODEL", "qwen3:8b"),
    },
    "zai": {
        "base_url": os.getenv("ZAI_BASE_URL", ""),
        "api_key":  os.getenv("ZAI_API_KEY", ""),
        "model":    os.getenv("ZAI_MODEL", ""),
    },
}

if LLM_PROVIDER not in _PROVIDER_DEFAULTS:
    raise ValueError(f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. Choose 'zai' or 'ollama'.")

_cfg = _PROVIDER_DEFAULTS[LLM_PROVIDER]
LLM_BASE_URL: str = _cfg["base_url"]
LLM_API_KEY:  str = _cfg["api_key"]
LLM_MODEL:    str = _cfg["model"]

LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "2"))
LLM_RETRY_BASE_DELAY_SECONDS = float(os.getenv("LLM_RETRY_BASE_DELAY_SECONDS", "1"))

_JSON_LD_MAX_CHARS = 4000
_LLM_MAX_TOKENS = 3072

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Lazily create the AsyncOpenAI client to avoid binding to
    the wrong event loop when imported at module level under Twisted."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Schema helpers — resolve $defs/$ref so small models see a flat schema
# ---------------------------------------------------------------------------

def _resolve_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively replace ``{"$ref": "#/$defs/Name"}`` with the actual definition."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].rsplit("/", 1)[-1]
            resolved = defs.get(ref_name, node)
            # Recursively resolve in case the definition itself has $ref
            return _resolve_refs(copy.deepcopy(resolved), defs)
        return {k: _resolve_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(item, defs) for item in node]
    return node


def _build_flat_schema() -> dict[str, Any]:
    """Return the PageAudit JSON schema with all ``$defs`` inlined and
    injected fields (url, meta_tags, headers, image_stats) removed."""
    schema = copy.deepcopy(PageAudit.model_json_schema())
    defs = schema.pop("$defs", {})
    schema = _resolve_refs(schema, defs)

    # Drop fields the LLM should NOT produce (they are injected post-hoc)
    _injected = {
        "url", "meta_tags", "headers", "image_stats",
        # Spider-computed dimensions (no LLM involvement)
        "performance", "security", "canonical_analysis",
        # Computed properties
        "overall_score", "letter_grade",
    }
    for field in list(_injected):
        schema.get("properties", {}).pop(field, None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in _injected]

    # For LLM-scored dimensions that also carry spider-injected sub-fields,
    # strip those sub-fields from the schema so the LLM only produces what it should.
    _link_spider_fields = {"internal_links", "external_links", "nofollow_count", "broken_links"}
    link_props = schema.get("properties", {}).get("link_analysis", {}).get("properties", {})
    for f in _link_spider_fields:
        link_props.pop(f, None)
    link_req = schema.get("properties", {}).get("link_analysis", {}).get("required", [])
    if link_req:
        schema["properties"]["link_analysis"]["required"] = [
            r for r in link_req if r not in _link_spider_fields
        ]

    _read_spider_fields = {"word_count", "thin_content"}
    read_props = schema.get("properties", {}).get("readability", {}).get("properties", {})
    for f in _read_spider_fields:
        read_props.pop(f, None)
    read_req = schema.get("properties", {}).get("readability", {}).get("required", [])
    if read_req:
        schema["properties"]["readability"]["required"] = [
            r for r in read_req if r not in _read_spider_fields
        ]

    _a11y_spider_fields = {"has_skip_nav", "aria_landmark_count", "form_labels_missing"}
    a11y_props = schema.get("properties", {}).get("accessibility", {}).get("properties", {})
    for f in _a11y_spider_fields:
        a11y_props.pop(f, None)
    a11y_req = schema.get("properties", {}).get("accessibility", {}).get("required", [])
    if a11y_req:
        schema["properties"]["accessibility"]["required"] = [
            r for r in a11y_req if r not in _a11y_spider_fields
        ]

    return schema

# Cache the flattened schema — it never changes at runtime.
_FLAT_SCHEMA: dict[str, Any] | None = None

def _get_flat_schema() -> dict[str, Any]:
    global _FLAT_SCHEMA
    if _FLAT_SCHEMA is None:
        _FLAT_SCHEMA = _build_flat_schema()
    return _FLAT_SCHEMA


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert technical SEO auditor. You analyze web pages and output \
a JSON object that strictly matches the schema provided below. Do NOT \
include any keys other than those in the schema. Do NOT wrap the JSON in \
markdown code fences.

SCORING RUBRIC (all scores are integers 0-100):
- 0   = completely missing or critically broken
- 25  = present but severely deficient
- 50  = partially implemented, notable gaps
- 75  = mostly correct, minor improvements needed
- 100 = best practice fully implemented

IMPORTANT schema_analysis scoring rules:
- If NO JSON-LD schemas are detected, schema_analysis.score MUST be 0.
- Score above 50 ONLY when valid, relevant structured data is present and reasonably complete.

severity must be exactly one of: "high", "medium", "low".

DIMENSIONS YOU MUST SCORE:
1. semantic_analysis -- header hierarchy, content-title match, on-page SEO issues.
2. schema_analysis -- JSON-LD quality. score=0 when no JSON-LD.
3. content_analysis -- direct-answer availability and conciseness.
4. link_analysis -- evaluate anchor text quality, link distribution, and issues. \
You receive link counts as context; score the QUALITATIVE aspects.
5. readability -- reading level, keyword usage, content quality. \
You receive word_count as context; provide reading_level (e.g. "Grade 8"), \
keyword_density_notes, and a score.
6. accessibility -- evaluate the page for basic a11y: color contrast hints, \
semantic HTML usage, ARIA utilisation. You receive structural stats as context.

Dimensions you do NOT score (they are auto-computed):
- performance, security, canonical_analysis -- do NOT include these.

EXAMPLE OUTPUT:
{
  "semantic_analysis": {
    "score": 30,
    "issues": [
      {"severity": "high", "description": "Missing H1 heading tag.", "suggested_fix": "Add a single descriptive H1 element."},
      {"severity": "medium", "description": "Heading hierarchy skips from H2 to H4.", "suggested_fix": "Use sequential heading levels without gaps."}
    ]
  },
  "schema_analysis": {
    "score": 0,
    "detected_types": [],
    "missing_fields": []
  },
  "content_analysis": {
    "score": 45,
    "has_direct_answer": false,
    "answer_snippet": null
  },
  "link_analysis": {
    "score": 60,
    "issues": [
      {"severity": "medium", "description": "Most anchor texts are generic (click here).", "suggested_fix": "Use descriptive anchor text."}
    ]
  },
  "readability": {
    "score": 55,
    "reading_level": "Grade 10",
    "keyword_density_notes": "Primary keyword appears only once in 1200 words.",
    "issues": []
  },
  "accessibility": {
    "score": 40,
    "issues": [
      {"severity": "high", "description": "Images lack alt text.", "suggested_fix": "Add descriptive alt attributes to all images."}
    ]
  }
}
"""

_USER_MSG_TEMPLATE = """\
Analyze this page for SEO: {url}

META TAGS: {meta_tags}
HEADERS: {headers}
IMAGE STATS: {image_stats}
JSON-LD: {json_ld}

LINK STATS: internal={internal_links}, external={external_links}, nofollow={nofollow_count}
WORD COUNT: {word_count}
ACCESSIBILITY STATS: skip_nav={has_skip_nav}, aria_landmarks={aria_landmarks}, form_labels_missing={form_labels_missing}

HTML SNIPPET (Cleaned):
{html}

TEXT CONTENT:
{text}

Return ONLY a JSON object matching the following schema. Do NOT include \
url, meta_tags, headers, image_stats, performance, security, or \
canonical_analysis -- they are injected automatically.

{schema}

Evaluate these 6 dimensions:
1. semantic_analysis -- header hierarchy, content-title match, SEO issues.
2. schema_analysis -- JSON-LD quality. If no JSON-LD detected, score MUST be 0.
3. content_analysis -- direct-answer availability and conciseness.
4. link_analysis -- anchor text quality, link distribution issues (score + issues array).
5. readability -- reading_level, keyword_density_notes, score, issues array.
6. accessibility -- a11y issues, score, issues array.
"""


async def analyze_with_llm(
    url: str,
    html: str,
    json_ld: list[dict],
    text: str,
    meta_tags: MetaTags,
    headers: HeaderStructure,
    image_stats: ImageStats,
    link_analysis: LinkAnalysis,
    performance: PerformanceMetrics,
    readability: ReadabilityAnalysis,
    security: SecurityCheck,
    accessibility: AccessibilityAnalysis,
    canonical_analysis: CanonicalAnalysis,
    timeout_seconds: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_base_delay: Optional[float] = None,
    logger: Optional[logging.Logger] = None,
) -> PageAudit:
    """Analyze page content using the configured LLM and return a validated PageAudit."""

    flat_schema = _get_flat_schema()

    user_msg = _USER_MSG_TEMPLATE.format(
        url=url,
        meta_tags=meta_tags.model_dump_json(),
        headers=headers.model_dump_json(),
        image_stats=image_stats.model_dump_json(),
        json_ld=json.dumps(json_ld, indent=2)[:_JSON_LD_MAX_CHARS],
        html=html,
        text=text,
        internal_links=link_analysis.internal_links,
        external_links=link_analysis.external_links,
        nofollow_count=link_analysis.nofollow_count,
        word_count=readability.word_count,
        has_skip_nav=accessibility.has_skip_nav,
        aria_landmarks=accessibility.aria_landmark_count,
        form_labels_missing=accessibility.form_labels_missing,
        schema=json.dumps(flat_schema, indent=2),
    )

    timeout_seconds = timeout_seconds if timeout_seconds is not None else LLM_TIMEOUT_SECONDS
    retry_attempts = retry_attempts if retry_attempts is not None else LLM_RETRY_ATTEMPTS
    retry_base_delay = retry_base_delay if retry_base_delay is not None else LLM_RETRY_BASE_DELAY_SECONDS
    last_error: Optional[Exception] = None
    data: Optional[dict] = None
    client = _get_client()

    for attempt in range(retry_attempts + 1):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=_LLM_MAX_TOKENS,
                ),
                timeout=timeout_seconds,
            )

            raw_json = response.choices[0].message.content
            if not raw_json:
                raise ValueError("Empty response from LLM")

            data = json.loads(raw_json)
            break
        except (
            asyncio.TimeoutError,
            ValueError,
            json.JSONDecodeError,
            openai.APIError,
            openai.APIConnectionError,
            openai.RateLimitError,
        ) as exc:
            last_error = exc
            if logger:
                logger.warning(
                    "LLM request failed on attempt %s/%s for %s: %s",
                    attempt + 1,
                    retry_attempts + 1,
                    url,
                    exc,
                )
            if attempt < retry_attempts:
                await asyncio.sleep(retry_base_delay * (2 ** attempt))
            else:
                break

    if data is None:
        fallback_issue = {
            "severity": "high",
            "description": f"LLM analysis failed: {last_error}",
            "suggested_fix": "Retry the audit or inspect the LLM service logs.",
        }
        data = {
            "semantic_analysis": {"score": 0, "issues": [fallback_issue]},
            "schema_analysis": {"score": 0, "detected_types": [], "missing_fields": []},
            "content_analysis": {"score": 0, "has_direct_answer": False, "answer_snippet": None},
            "link_analysis": {"score": 0, "issues": []},
            "readability": {"score": 0, "reading_level": None, "keyword_density_notes": None, "issues": []},
            "accessibility": {"score": 0, "issues": []},
        }

    # Backfill defaults for any top-level fields the LLM omitted
    _FIELD_DEFAULTS: dict[str, Any] = {
        "semantic_analysis": {"score": 0, "issues": []},
        "schema_analysis":   {"score": 0, "detected_types": [], "missing_fields": []},
        "content_analysis":  {"score": 0, "has_direct_answer": False, "answer_snippet": None},
        "link_analysis":     {"score": 0, "issues": []},
        "readability":       {"score": 0, "reading_level": None, "keyword_density_notes": None, "issues": []},
        "accessibility":     {"score": 0, "issues": []},
    }
    for key, default in _FIELD_DEFAULTS.items():
        if key not in data:
            if logger:
                logger.warning("LLM response missing '%s' for %s — using defaults", key, url)
            data[key] = default

    # --- Merge spider-extracted sub-fields into LLM-scored dimensions ---
    # link_analysis: LLM provides score+issues; spider provides counts
    la = data.get("link_analysis", {})
    la["internal_links"] = link_analysis.internal_links
    la["external_links"] = link_analysis.external_links
    la["nofollow_count"] = link_analysis.nofollow_count
    la["broken_links"] = link_analysis.broken_links
    data["link_analysis"] = la

    # readability: LLM provides score+reading_level+keyword notes; spider provides word_count
    rd = data.get("readability", {})
    rd["word_count"] = readability.word_count
    data["readability"] = rd

    # accessibility: LLM provides score+issues; spider provides structural data
    a11y = data.get("accessibility", {})
    a11y["has_skip_nav"] = accessibility.has_skip_nav
    a11y["aria_landmark_count"] = accessibility.aria_landmark_count
    a11y["form_labels_missing"] = accessibility.form_labels_missing
    data["accessibility"] = a11y

    # Inject fully spider-computed fields
    data["url"] = url
    data["meta_tags"] = meta_tags.model_dump()
    data["headers"] = headers.model_dump()
    data["image_stats"] = image_stats.model_dump()
    data["performance"] = performance.model_dump()
    data["security"] = security.model_dump()
    data["canonical_analysis"] = canonical_analysis.model_dump()

    # Validate with Pydantic (also enforces business rules like schema score → 0)
    return PageAudit.model_validate(data)
