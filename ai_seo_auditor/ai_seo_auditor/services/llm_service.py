import asyncio
import copy
import json
import logging
import os
from typing import Any, Optional

import openai
from dotenv import load_dotenv
from openai import AsyncOpenAI

from ai_seo_auditor.models.schemas import PageAudit, MetaTags, HeaderStructure, ImageStats

# ---------------------------------------------------------------------------
# Environment / defaults
# ---------------------------------------------------------------------------
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
OLLAMA_RETRY_ATTEMPTS = int(os.getenv("OLLAMA_RETRY_ATTEMPTS", "2"))
OLLAMA_RETRY_BASE_DELAY_SECONDS = float(os.getenv("OLLAMA_RETRY_BASE_DELAY_SECONDS", "1"))

_JSON_LD_MAX_CHARS = 4000
_LLM_MAX_TOKENS = 2048

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Lazily create the AsyncOpenAI client to avoid binding to
    the wrong event loop when imported at module level under Twisted."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
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
    _injected = {"url", "meta_tags", "headers", "image_stats"}
    for field in list(_injected):
        schema.get("properties", {}).pop(field, None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in _injected]

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

EXAMPLE OUTPUT (for a page with no JSON-LD and a missing H1):
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
  }
}
"""

_USER_MSG_TEMPLATE = """\
Analyze this page for SEO: {url}

META TAGS: {meta_tags}
HEADERS: {headers}
IMAGE STATS: {image_stats}
JSON-LD: {json_ld}

HTML SNIPPET (Cleaned):
{html}

TEXT CONTENT:
{text}

Return ONLY a JSON object matching the following schema. Do NOT include \
url, meta_tags, headers, or image_stats — they are injected automatically.

{schema}

Evaluate:
1. semantic_analysis — header hierarchy, content-title match, SEO issues.
2. schema_analysis — JSON-LD quality. If no JSON-LD detected, score MUST be 0.
3. content_analysis — direct-answer availability and conciseness.
"""


async def analyze_with_ollama(
    url: str,
    html: str,
    json_ld: list[dict],
    text: str,
    meta_tags: MetaTags,
    headers: HeaderStructure,
    image_stats: ImageStats,
    timeout_seconds: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_base_delay: Optional[float] = None,
    logger: Optional[logging.Logger] = None,
) -> PageAudit:
    """Analyze page content using Ollama and return a validated PageAudit."""

    flat_schema = _get_flat_schema()

    user_msg = _USER_MSG_TEMPLATE.format(
        url=url,
        meta_tags=meta_tags.model_dump_json(),
        headers=headers.model_dump_json(),
        image_stats=image_stats.model_dump_json(),
        json_ld=json.dumps(json_ld, indent=2)[:_JSON_LD_MAX_CHARS],
        html=html,
        text=text,
        schema=json.dumps(flat_schema, indent=2),
    )

    timeout_seconds = timeout_seconds if timeout_seconds is not None else OLLAMA_TIMEOUT_SECONDS
    retry_attempts = retry_attempts if retry_attempts is not None else OLLAMA_RETRY_ATTEMPTS
    retry_base_delay = retry_base_delay if retry_base_delay is not None else OLLAMA_RETRY_BASE_DELAY_SECONDS
    last_error: Optional[Exception] = None
    data: Optional[dict] = None
    client = _get_client()

    for attempt in range(retry_attempts + 1):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=OLLAMA_MODEL,
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
        }

    # Inject fields extracted by the spider — the LLM is told NOT to produce these.
    data["url"] = url
    data["meta_tags"] = meta_tags.model_dump()
    data["headers"] = headers.model_dump()
    data["image_stats"] = image_stats.model_dump()

    # Validate with Pydantic (also enforces business rules like schema score → 0)
    return PageAudit.model_validate(data)
