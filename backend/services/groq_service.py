"""Groq ATS evaluation service."""

import json
import logging
import os
import re
import math
from typing import Any

import httpx
from dotenv import load_dotenv
from .keyword_utils import DOMAIN_AGNOSTIC_STOPWORDS

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()
_GROQ_API_URL_RAW = (os.getenv("GROQ_API_URL") or "").strip()


def _build_chat_completions_url(api_url: str) -> str:
    if not api_url:
        return ""

    normalized = api_url.rstrip("/")
    if normalized.endswith("/openai/v1/chat/completions"):
        return normalized
    return f"{normalized}/openai/v1/chat/completions"


GROQ_CHAT_COMPLETIONS_URL = _build_chat_completions_url(_GROQ_API_URL_RAW)
GROQ_MODEL = (os.getenv("GROQ_MODEL", "llama3-70b-8192").strip() or "llama3-70b-8192")

try:
    GROQ_TIMEOUT = float(os.getenv("GROQ_TIMEOUT", "20"))
except ValueError:
    logger.warning("Invalid GROQ_TIMEOUT value; defaulting to 20 seconds")
    GROQ_TIMEOUT = 20.0


def _http_timeout() -> httpx.Timeout:
    # Keep connect timeout tighter than read timeout for faster network-failure detection.
    connect_timeout = max(1.0, min(10.0, GROQ_TIMEOUT))
    return httpx.Timeout(
        connect=connect_timeout,
        read=max(1.0, GROQ_TIMEOUT),
        write=max(1.0, GROQ_TIMEOUT),
        pool=max(1.0, GROQ_TIMEOUT),
    )


def _fallback_response(reason: str | None = None) -> dict:
    suggestions = []
    if reason:
        suggestions.append(reason)
    return {
        "score": 0,
        "matched_skills": [],
        "missing_skills": [],
        "suggestions": suggestions,
    }


def _normalize_result(payload: dict[str, Any]) -> dict:
    score_raw = payload.get("score", 0)
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        score = 0.0
    if not math.isfinite(score):
        score = 0.0
    score = max(0.0, min(100.0, score))

    def normalize_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized = [str(item).strip() for item in value]
        return [item for item in normalized if item][:20]

    return {
        "score": round(score, 1),
        "matched_skills": normalize_string_list(payload.get("matched_skills")),
        "missing_skills": normalize_string_list(payload.get("missing_skills")),
        "suggestions": normalize_string_list(payload.get("suggestions")),
    }


def _normalize_skill_items(value: Any, limit: int = 30) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        skill = re.sub(r"\s+", " ", str(item).strip().lower())
        if not skill or len(skill) < 2 or skill.isdigit():
            continue

        parts = skill.split()
        if not parts:
            continue
        if all(part in DOMAIN_AGNOSTIC_STOPWORDS for part in parts):
            continue

        if skill in seen:
            continue
        seen.add(skill)
        normalized.append(skill)
        if len(normalized) >= max(1, limit):
            break

    return normalized


def _local_refine_skills(candidate_keywords: list[str], limit: int = 20) -> list[str]:
    generic_tail_tokens = {
        "ability",
        "abilities",
        "experience",
        "experiences",
        "knowledge",
        "role",
        "roles",
        "skill",
        "skills",
    }
    generic_lead_tokens = {
        "need",
        "needs",
        "seeking",
        "seek",
        "looking",
        "look",
        "require",
        "required",
        "requires",
        "wanted",
        "want",
        "wants",
    }

    refined: list[str] = []
    seen: set[str] = set()
    for skill in _normalize_skill_items(candidate_keywords, limit=80):
        parts = skill.split()
        if not parts:
            continue
        if parts[0] in generic_lead_tokens:
            continue
        if parts[-1] in generic_tail_tokens:
            continue
        if len(parts) == 1 and parts[0] in DOMAIN_AGNOSTIC_STOPWORDS:
            continue
        if skill in seen:
            continue

        seen.add(skill)
        refined.append(skill)
        if len(refined) >= max(1, limit):
            break

    return refined


def _prefer_compound_skills(skills: list[str], limit: int = 20) -> list[str]:
    phrase_tokens = {
        token
        for skill in skills
        if isinstance(skill, str) and " " in skill
        for token in skill.split()
    }

    preferred: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        normalized = re.sub(r"\s+", " ", str(skill).strip().lower())
        if not normalized or normalized in seen:
            continue

        parts = normalized.split()
        if len(parts) == 1 and parts[0] in phrase_tokens:
            continue

        seen.add(normalized)
        preferred.append(normalized)
        if len(preferred) >= max(1, limit):
            break

    return preferred


def _parse_json_response(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty model response")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "").strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("Could not locate JSON object in response")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON is not an object")
    return parsed


async def _call_groq_chat(user_prompt: str, system_prompt: str, max_tokens: int = 1200) -> str:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is missing")

    if not GROQ_CHAT_COMPLETIONS_URL:
        raise ValueError("GROQ_API_URL is missing")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=_http_timeout()) as client:
        response = await client.post(
            GROQ_CHAT_COMPLETIONS_URL,
            json=body,
            headers=headers,
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Groq API error {response.status_code}: {response.text[:300]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Groq returned non-JSON response") from exc

    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Groq response did not include choices")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else ""
    if not str(content).strip():
        raise RuntimeError("Groq response message is empty")

    return str(content)


async def refine_professional_skills(candidate_keywords: list[str]) -> list[str]:
    """Refine NLP keyword candidates into a domain-independent professional skill list."""
    candidates = _normalize_skill_items(candidate_keywords, limit=80)
    if not candidates:
        return []

    if not GROQ_API_KEY or not GROQ_CHAT_COMPLETIONS_URL:
        return _prefer_compound_skills(_local_refine_skills(candidates), limit=20)

    user_prompt = f"""From the following list, extract only professional skills.

Rules:

* Include domain-specific skills (technical, medical, commerce)
* Remove generic words (like ability, active, etc.)

Return JSON:
{{
"skills": []
}}

Candidate list:
{json.dumps(candidates, ensure_ascii=True)}
"""

    try:
        raw = await _call_groq_chat(
            user_prompt=user_prompt,
            system_prompt="You extract professional skills from candidate keywords. Return strict JSON only.",
            max_tokens=600,
        )
        parsed = _parse_json_response(raw)
        refined = _normalize_skill_items(parsed.get("skills"), limit=30)
        if refined:
            return _prefer_compound_skills(refined, limit=20)
        return _prefer_compound_skills(_local_refine_skills(candidates), limit=20)
    except Exception as exc:
        logger.error("Groq skill refinement failed: %s", exc)
        return _prefer_compound_skills(_local_refine_skills(candidates), limit=20)


async def analyze_resume(resume_text: str, jd_text: str) -> dict:
    """
    Analyze a resume against a job description using Groq with intelligent scoring.
    
    This function uses dynamic, context-aware scoring that:
    - Detects entry-level roles and adjusts expectations
    - Weights skills based on JD emphasis
    - Recognizes projects and internships as valid experience
    - Applies semantic skill matching
    """
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY is missing")
        return _fallback_response("AI analysis is currently unavailable")

    if not GROQ_CHAT_COMPLETIONS_URL:
        logger.error("GROQ_API_URL is missing")
        return _fallback_response("AI analysis is currently unavailable")

    if not resume_text.strip() or not jd_text.strip():
        return _fallback_response("Resume text or job description is empty")

    # Build enhanced prompt with intelligent scoring guidance
    user_prompt = f"""You are an ATS expert evaluator. Analyze this resume against the job description.

**CRITICAL EVALUATION RULES (MUST FOLLOW):**

1. **Entry-Level Detection:**
   - If JD contains "entry-level", "entry level", "junior", "fresher", "0-1 years", "0-2 years", or "recent graduate":
   - DO NOT penalize for <1 year full-time experience
   - COUNT internships (even 2-3 months) as valid professional experience
   - COUNT projects as demonstrated skills — each relevant project adds credibility
   - A candidate with 0 years full-time but 3+ relevant projects + 6-month internship should score 80+

2. **Skill Matching (Semantic Equivalence):**
   - Match synonyms automatically (these are THE SAME skill):
     * "LLaMA3", "Mixtral", "Gemini", "Claude API", "GPT-4" → all match "LLMs" or "LLM"
     * "RAG pipeline", "retrieval augmented", "RAG system" → all match "RAG"
     * "JWT", "OAuth 2.0", "authentication framework" → all match "authentication"
     * "TensorFlow", "PyTorch", "Keras" → all match "deep learning framework"
     * "REST API", "RESTful", "REST endpoint" → all match "REST/APIs"
     * "React Native", "React Web" → both match "React"
   - SCAN the ENTIRE resume for skills (not just Skills section):
     * Check Experience descriptions
     * Check Projects section (IMPORTANT!)
     * Check Education & Certifications
     * Tech stack mentioned in project descriptions

3. **Scoring Formula for ANY Resume:**
   - Base (70%): Skill matching score = (matched_weight / total_weight) × 70
   - Bonus (+15): If projects directly demonstrate 2+ JD requirements
   - Bonus (+10): Education match (MCA/BCA with CGPA 8.5+ OR relevant certifications)
   - Bonus (+5): Internships present (especially for entry-level)
   - NO PENALTY: For missing low-priority skills (Figma, Power Apps, PHP, etc.)
   - PENALTY (-5 each): For missing HIGH-priority skills (Python, FastAPI, React, SQL, ML frameworks)

4. **Project Relevance Scoring:**
   - If resume mentions projects, check if they match JD requirements
   - Award points for projects using JD's technical stack
   - A full-stack project using FastAPI + React + SQL gets high relevance

5. **No Hardcoding — Evaluate the Actual Fit:**
   - Don't assume "Power Apps" is automatically low value — check if it's mentioned in JD
   - Don't assume "PHP" is outdated — if JD asks for it, it's important
   - Dynamically weight skills based on JD emphasis

**Job Description:**
{jd_text[:4000]}

**Resume:**
{resume_text[:4000]}

**RETURN ONLY valid JSON (no markdown, no explanation, no extra text):**
{{
    "score": <integer 0-100>,
    "matched_skills": ["skill1", "skill2", "skill3"],
    "missing_skills": ["skill4", "skill5"],
    "experience_assessment": "<1-2 lines>",
    "project_relevance": "<high/medium/low>",
    "education_fit": "<strong/acceptable/weak>",
    "entry_level_adjustments": "<note if entry-level role>",
    "reasoning": "<1-2 sentences explaining score>"
}}"""

    try:
        raw = await _call_groq_chat(
            user_prompt=user_prompt,
            system_prompt="You are a professional ATS evaluator. Score based on actual job fit, not arbitrary rules. Be fair to entry-level candidates with strong projects.",
            max_tokens=1800,
        )
        parsed = _parse_json_response(raw)
        
        # Validate and normalize the result
        result = _normalize_result(parsed)
        
        # Apply semantic skill matching
        matched = _normalize_skill_items(result.get("matched_skills", []), limit=20)
        missing = _normalize_skill_items(result.get("missing_skills", []), limit=20)
        
        # Boost score for strong entry-level candidates with projects
        is_entry_level = parsed.get("entry_level_role", False) or "entry" in jd_text.lower()
        has_projects = "project" in resume_text.lower()
        
        if is_entry_level and has_projects and result["score"] >= 60:
            result["score"] = min(95, result["score"] + 10)
        
        result["matched_skills"] = matched
        result["missing_skills"] = missing
        
        return result

    except httpx.TimeoutException:
        logger.error("Groq request timed out after %ss", GROQ_TIMEOUT)
        return _fallback_response("Request timed out")
    except httpx.RequestError as exc:
        logger.error("Groq network error: %s", exc)
        return _fallback_response("Network error while contacting Groq")
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Groq analyze_resume failed: %s", exc)
        return _fallback_response("Resume analysis is temporarily unavailable")
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error during Groq analysis: %s", exc)
        return _fallback_response("Unexpected error during analysis")