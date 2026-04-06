"""
LLM Service with Fallback Support

Implements three-tier fallback:
1. Primary: Configured provider (ollama/groq) — structured output
2. Fallback: Alternative provider (groq/openai) if primary fails
3. Final: Default structured response if all LLM calls fail

Supports providers:
  - "ollama" : local Ollama server (free, private)
  - "groq"   : Groq Cloud API (fast, requires GROQ_API_KEY)
"""

import httpx
import json
import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = os.getenv("PROVIDER", "ollama")

# ── Ollama config ────────────────────────────────────────────────────────────
OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma:2b")

# ── Groq config ──────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama3-8b-8192")

# ── OpenAI config (fallback) ──────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_URL     = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

VALID_PROVIDERS = {"ollama", "groq"}

# ── Advanced ATS Prompt (Structured Output) ───────────────────────────────────
ADVANCED_ATS_PROMPT = """You are an expert ATS (Applicant Tracking System) resume analyst.

Analyze the resume against the job description and provide a detailed structured evaluation.

RESPOND ONLY WITH VALID JSON (no markdown, no code blocks, no extra text):
{{
  "overall_score": <0-100>,
  "skill_match": <0-100>,
  "education_match": <0-100>,
  "experience_match": <0-100>,
  "missing_skills": ["skill1", "skill2", "skill3"],
  "education_gap": "<brief description or 'None'>",
  "experience_gap": "<brief description or 'None'>",
  "feedback": "<2-3 sentence summary>"
}}

JOB DESCRIPTION:
{job_description}

RESUME:
{resume_text}
"""

# ── Default response (used when LLM fails) ───────────────────────────────────
DEFAULT_RESPONSE = {
    "overall_score": 50,
    "skill_match": 50,
    "education_match": 50,
    "experience_match": 50,
    "missing_skills": ["Please review manually"],
    "education_gap": "Unable to assess",
    "experience_gap": "Unable to assess",
    "feedback": "LLM service unavailable. Please try again or contact support.",
}


# ── JSON extraction helper ────────────────────────────────────────────────────
def _parse_llm_json(raw_text: str) -> dict:
    """Try progressively looser strategies to extract valid JSON from LLM output."""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Remove code fences
    cleaned = re.sub(r"```(?:json)?", "", raw_text).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            # Validate required fields
            if all(k in parsed for k in ["overall_score", "missing_skills"]):
                return parsed
        except json.JSONDecodeError:
            pass

    logger.warning(f"Failed to parse LLM JSON response: {raw_text[:200]}")
    return DEFAULT_RESPONSE


# ── Provider implementations ──────────────────────────────────────────────────
async def _call_ollama(prompt: str) -> str:
    """Call local Ollama server."""
    logger.info(f"Calling Ollama ({OLLAMA_MODEL})")
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1000},
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(OLLAMA_URL, json=payload)
            r.raise_for_status()
            response = r.json().get("response", "")
            logger.info(f"Ollama response: {len(response)} chars")
            return response
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        raise


async def _call_groq(prompt: str) -> str:
    """Call Groq Cloud API."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not configured")

    logger.info(f"Calling Groq ({GROQ_MODEL})")
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(GROQ_URL, json=payload, headers=headers)
            r.raise_for_status()
            response = r.json()["choices"][0]["message"]["content"]
            logger.info(f"Groq response: {len(response)} chars")
            return response
    except Exception as e:
        logger.error(f"Groq call failed: {e}")
        raise


async def _call_openai(prompt: str) -> str:
    """Call OpenAI API (fallback)."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured")

    logger.info(f"Calling OpenAI ({OPENAI_MODEL})")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(OPENAI_URL, json=payload, headers=headers)
            r.raise_for_status()
            response = r.json()["choices"][0]["message"]["content"]
            logger.info(f"OpenAI response: {len(response)} chars")
            return response
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        raise


# ── Public interface with fallback ────────────────────────────────────────────
async def analyze_resume(
    job_description: str,
    resume_text: str,
    provider: str = None,
) -> dict:
    """
    Analyze resume vs job description with three-tier fallback.

    Fallback chain:
    1. Primary provider (ollama/groq)
    2. Alternative provider (groq/openai)
    3. Default structured response

    Args:
        job_description: Full JD text
        resume_text: Extracted resume text
        provider: "ollama" | "groq" | None (uses DEFAULT_PROVIDER)

    Returns:
        dict with keys:
            - overall_score (0-100)
            - skill_match (0-100)
            - education_match (0-100)
            - experience_match (0-100)
            - missing_skills (list)
            - education_gap (str)
            - experience_gap (str)
            - feedback (str)
    """
    provider = provider or DEFAULT_PROVIDER
    logger.info(f"Starting analysis with provider: {provider}")

    # Validate inputs
    jd_len = len(job_description.strip())
    resume_len = len(resume_text.strip())
    
    if jd_len == 0:
        logger.warning("Empty job description")
        return {**DEFAULT_RESPONSE, "feedback": "Job description is empty"}
    if resume_len == 0:
        logger.warning("Empty resume")
        return {**DEFAULT_RESPONSE, "feedback": "Resume is empty"}

    logger.info(f"JD length: {jd_len}, Resume length: {resume_len}")

    prompt = ADVANCED_ATS_PROMPT.format(
        job_description=job_description[:5000],
        resume_text=resume_text[:5000],
    )

    # Try primary provider
    if provider == "groq":
        try:
            raw = await _call_groq(prompt)
            result = _parse_llm_json(raw)
            logger.info("Analysis successful (Groq)")
            return result if result else DEFAULT_RESPONSE
        except Exception as e:
            logger.warning(f"Groq failed ({e}), attempting fallback")

            # Fallback to Ollama or OpenAI
            try:
                if OLLAMA_URL and OLLAMA_URL != "":
                    raw = await _call_ollama(prompt)
                    result = _parse_llm_json(raw)
                    logger.info("Analysis successful (Ollama fallback)")
                    return result if result else DEFAULT_RESPONSE
            except Exception as e2:
                logger.warning(f"Ollama fallback failed ({e2})")

            # Final fallback to OpenAI
            if OPENAI_API_KEY:
                try:
                    raw = await _call_openai(prompt)
                    result = _parse_llm_json(raw)
                    logger.info("Analysis successful (OpenAI fallback)")
                    return result if result else DEFAULT_RESPONSE
                except Exception as e3:
                    logger.error(f"OpenAI fallback failed ({e3})")

    else:  # provider == "ollama"
        try:
            raw = await _call_ollama(prompt)
            result = _parse_llm_json(raw)
            logger.info("Analysis successful (Ollama)")
            return result if result else DEFAULT_RESPONSE
        except Exception as e:
            logger.warning(f"Ollama failed ({e}), attempting fallback")

            # Fallback to Groq or OpenAI
            if GROQ_API_KEY:
                try:
                    raw = await _call_groq(prompt)
                    result = _parse_llm_json(raw)
                    logger.info("Analysis successful (Groq fallback)")
                    return result if result else DEFAULT_RESPONSE
                except Exception as e2:
                    logger.warning(f"Groq fallback failed ({e2})")

            # Final fallback to OpenAI
            if OPENAI_API_KEY:
                try:
                    raw = await _call_openai(prompt)
                    result = _parse_llm_json(raw)
                    logger.info("Analysis successful (OpenAI fallback)")
                    return result if result else DEFAULT_RESPONSE
                except Exception as e3:
                    logger.error(f"OpenAI fallback failed ({e3})")

    logger.error("All LLM providers failed, returning default response")
    return DEFAULT_RESPONSE


async def list_groq_models() -> list[str]:
    """Return available Groq model IDs (requires GROQ_API_KEY)."""
    if not GROQ_API_KEY:
        return []
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("https://api.groq.com/openai/v1/models", headers=headers)
            r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
    except Exception:
        return []