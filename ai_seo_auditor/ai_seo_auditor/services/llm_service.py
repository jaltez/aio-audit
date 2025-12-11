import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv
from ai_seo_auditor.models.schemas import PageAudit

# Load environment variables
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)

SYSTEM_PROMPT = """
You are an expert technical SEO auditor.
You strictly output JSON matching the requested schema.
"""

async def analyze_with_ollama(url: str, html: str, json_ld: list, text: str) -> PageAudit:
    """
    Analyzes the page content using Ollama and returns a validated PageAudit object.
    """
    # Construct a prompt that forces the structure
    # We truncate inputs to avoid context limit issues
    user_msg = f"""
    Analyze this page: {url}

    HTML SNIPPET: {html[:2000]}...
    JSON-LD: {json_ld}
    TEXT: {text[:1000]}...

    Return a JSON object with:
    1. semantic_analysis (score 0-100, issues list)
    2. schema_analysis (score 0-100, detected_types, missing_fields)
    3. content_analysis (score 0-100, has_direct_answer bool, answer_snippet)

    Ensure the output is valid JSON and matches the structure:
    {{
        "url": "{url}",
        "semantic_analysis": {{ "score": int, "issues": [ {{ "severity": "high|medium|low", "description": "...", "suggested_fix": "..." }} ] }},
        "schema_analysis": {{ "score": int, "detected_types": [...], "missing_fields": [...] }},
        "content_analysis": {{ "score": int, "has_direct_answer": bool, "answer_snippet": "..." }}
    }}
    """

    try:
        response = await client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg}
            ],
            response_format={"type": "json_object"}
        )

        raw_json = response.choices[0].message.content
        if not raw_json:
            raise ValueError("Empty response from LLM")

        # Validate with Pydantic
        return PageAudit.model_validate_json(raw_json)
    except Exception as e:
        # In a real scenario, we might want to return a partial result or retry
        print(f"Error analyzing {url}: {e}")
        # Return a dummy object or re-raise
        # For now, re-raising to see errors during development
        raise e
