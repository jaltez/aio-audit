import asyncio
import copy
import json
import logging
import os
from typing import Optional

import openai
from dotenv import load_dotenv
from openai import AsyncOpenAI

from ai_seo_auditor.models.schemas import PageAudit, MetaTags, HeaderStructure, ImageStats

# Load environment variables
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
OLLAMA_RETRY_ATTEMPTS = int(os.getenv("OLLAMA_RETRY_ATTEMPTS", "2"))
OLLAMA_RETRY_BASE_DELAY_SECONDS = float(os.getenv("OLLAMA_RETRY_BASE_DELAY_SECONDS", "1"))

_JSON_LD_MAX_CHARS = 4000

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Lazily create the AsyncOpenAI client to avoid binding to
    the wrong event loop when imported at module level under Twisted."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
    return _client

SYSTEM_PROMPT = """
You are an expert technical SEO auditor.
You strictly output JSON matching the requested schema.
"""

async def analyze_with_ollama(
    url: str,
    html: str,
    json_ld: list,
    text: str,
    meta_tags: MetaTags,
    headers: HeaderStructure,
    image_stats: ImageStats,
    timeout_seconds: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    retry_base_delay: Optional[float] = None,
    logger: Optional[logging.Logger] = None,
) -> PageAudit:
    """
    Analyzes the page content using Ollama and returns a validated PageAudit object.
    """
    # Deep-copy the schema so we don't mutate the Pydantic-cached version
    schema = copy.deepcopy(PageAudit.model_json_schema())
    # Remove fields we inject ourselves to avoid confusing the LLM
    for field in ["url", "meta_tags", "headers", "image_stats"]:
        schema.get("properties", {}).pop(field, None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in ["url", "meta_tags", "headers", "image_stats"]]

    # Construct a prompt that forces the structure
    user_msg = f"""
    Analyze this page for SEO: {url}

    META TAGS: {meta_tags.model_dump_json()}
    HEADERS: {headers.model_dump_json()}
    IMAGE STATS: {image_stats.model_dump_json()}
    JSON-LD: {json.dumps(json_ld, indent=2)[:_JSON_LD_MAX_CHARS]}

    HTML SNIPPET (Cleaned):
    {html}

    TEXT CONTENT:
    {text}

    Return a JSON object matching this schema:
    {json.dumps(schema, indent=2)}

    Evaluate the following:
    1. semantic_analysis: Check if headers are logical, content matches title, and identify SEO issues (missing H1, skipped heading levels, duplicate H1s, etc.).
    2. schema_analysis: Evaluate JSON-LD quality and completeness.
    3. content_analysis: Check for direct answers to potential user queries.

    SCORING RUBRIC (all scores are integers 0-100):
    - 0  = completely missing or critically broken
    - 25 = present but severely deficient
    - 50 = partially implemented, notable gaps
    - 75 = mostly correct, minor improvements needed
    - 100 = best practice fully implemented

    IMPORTANT schema_analysis scoring rules:
    - If NO JSON-LD schemas are detected, schema_analysis.score MUST be 0.
    - Score above 50 ONLY when valid, relevant structured data is present and reasonably complete.

    severity must be exactly one of: "high", "medium", "low".
    """

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
                ),
                timeout=timeout_seconds,
            )

            raw_json = response.choices[0].message.content
            if not raw_json:
                raise ValueError("Empty response from LLM")

            # Parse the response to ensure we can inject the extracted data if the LLM missed it
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
                await asyncio.sleep(retry_base_delay * (2**attempt))
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

    data["url"] = url
    data["meta_tags"] = meta_tags.model_dump()
    data["headers"] = headers.model_dump()
    data["image_stats"] = image_stats.model_dump()

    # Validate with Pydantic
    return PageAudit.model_validate(data)
