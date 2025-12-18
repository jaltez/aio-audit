import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv
from ai_seo_auditor.models.schemas import PageAudit, MetaTags, HeaderStructure, ImageStats

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

async def analyze_with_ollama(
    url: str, 
    html: str, 
    json_ld: list, 
    text: str,
    meta_tags: MetaTags,
    headers: HeaderStructure,
    image_stats: ImageStats
) -> PageAudit:
    """
    Analyzes the page content using Ollama and returns a validated PageAudit object.
    """
    # Get the schema to help the LLM
    schema = PageAudit.model_json_schema()
    # Remove fields we inject ourselves to avoid confusing the LLM
    for field in ["url", "meta_tags", "headers", "image_stats"]:
        if field in schema.get("properties", {}):
            del schema["properties"][field]
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in ["url", "meta_tags", "headers", "image_stats"]]

    # Construct a prompt that forces the structure
    # We truncate inputs to avoid context limit issues
    user_msg = f"""
    Analyze this page for SEO: {url}

    META TAGS: {meta_tags.model_dump_json()}
    HEADERS: {headers.model_dump_json()}
    IMAGE STATS: {image_stats.model_dump_json()}
    JSON-LD: {json_ld}
    
    HTML SNIPPET (Cleaned):
    {html[:8000]}...

    TEXT CONTENT:
    {text[:2000]}...

    Return a JSON object matching this schema:
    {json.dumps(schema, indent=2)}

    Evaluate the following:
    1. semantic_analysis: Check if headers are logical, content matches title, and identify SEO issues (missing H1, skipped levels, etc.).
    2. schema_analysis: Evaluate JSON-LD quality and completeness.
    3. content_analysis: Check for direct answers to potential user queries.

    Ensure all scores are integers between 0 and 100.
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

        # Parse the response to ensure we can inject the extracted data if the LLM missed it
        data = json.loads(raw_json)
        data["url"] = url
        data["meta_tags"] = meta_tags.model_dump()
        data["headers"] = headers.model_dump()
        data["image_stats"] = image_stats.model_dump()

        # Validate with Pydantic
        return PageAudit.model_validate(data)
    except Exception as e:
        # In a real scenario, we might want to return a partial result or retry
        print(f"Error analyzing {url}: {e}")
        # Return a dummy object or re-raise
        # For now, re-raising to see errors during development
        raise e
