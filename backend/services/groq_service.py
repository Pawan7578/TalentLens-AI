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
        "temperature": 0.0,  # Deterministic scoring: critical for consistent ATS results
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


# -- Strict ATS Scoring System --------------------------------------------------

STRICT_ATS_SYSTEM_PROMPT = """
You are a strict ATS (Applicant Tracking System) scoring engine.
Score the resume against the job description using this exact rubric:

SCORING RUBRIC (total = 100):
1. Keyword Match (25pts): Only count keywords explicitly required in the JD.
   Do NOT reward resume keywords absent from JD.
2. Role/Domain Alignment (20pts): Do the resume's domain and the JD's domain match?
3. Skills Match (20pts): Required skills present vs missing. Partial = half points.
4. Experience Match (20pts): 
   - If candidate has 0 years of required experience → MAX 5pts for this category.
   - Deduct 3pts for every missing year below the minimum.
5. Education (10pts): Check if education meets JD requirement.
6. Formatting/ATS-friendliness (5pts): Clean structure, standard headings.

HARD RULES (enforce strictly):
- If minimum experience requirement is NOT met → cap total score at 42.
- If domain is completely mismatched → cap total score at 45.
- Never give bonus points for skills not in the JD.
- Missing must-have skills = 0 pts for that skill.

Return ONLY valid JSON. No markdown outside JSON.
"""


async def extract_jd_keywords(jd_text: str) -> dict:
    """Extract ONLY required keywords from the JD using Groq."""
    extraction_prompt = f"""Extract keywords from this job description.
Return ONLY valid JSON:
{{
  "must_have": ["skill1", "skill2"],
  "good_to_have": ["skill3"],
  "domain": "<industry>"
}}

JOB DESCRIPTION:
{jd_text[:4000]}"""

    try:
        raw = await _call_groq_chat(
            user_prompt=extraction_prompt,
            system_prompt="Extract keywords. Return strict JSON only.",
            max_tokens=600,
        )
        result = _parse_json_response(raw)
        
        # Validate structure
        if not isinstance(result.get("must_have"), list):
            result["must_have"] = []
        if not isinstance(result.get("good_to_have"), list):
            result["good_to_have"] = []
        if not isinstance(result.get("domain"), str):
            result["domain"] = "General"
            
        return result
    except Exception as exc:
        logger.warning(f"JD keyword extraction failed: {exc}")
        return {"must_have": [], "good_to_have": [], "domain": "General"}


def apply_hard_rules(result: dict, jd_info: dict) -> dict:
    """Enforce Python-side hard caps regardless of LLM output."""
    score = result.get("score", 0)
    flags = result.get("flags", [])
    
    try:
        breakdown = result.get("breakdown", {})
        
        # Rule 1: Experience hard cap
        exp_match = breakdown.get("experience_match", {})
        required_yrs = exp_match.get("required_years", 0)
        candidate_yrs = exp_match.get("candidate_years", 0)
        
        if required_yrs > 0 and candidate_yrs == 0:
            score = min(score, 42)
            flags.append(f"⚠️ Hard cap: 0 of {required_yrs} required years → max 42")
            
        # Rule 2: Domain mismatch hard cap
        role_align = breakdown.get("role_alignment", {})
        role_score = role_align.get("score", 20)
        
        if role_score <= 5:
            score = min(score, 45)
            flags.append("⚠️ Hard cap: Major domain mismatch → max 45")
        
        result["score"] = int(score)
        result["flags"] = flags
        
        # Update rating
        if score < 40:
            result["rating"] = "Poor"
        elif score < 60:
            result["rating"] = "Average"
        elif score < 80:
            result["rating"] = "Good"
        else:
            result["rating"] = "Excellent"
            
    except Exception as exc:
        logger.warning(f"Error applying hard rules: {exc}")
        
    return result


async def analyze_resume(resume_text: str, jd_text: str) -> dict:
    """
    Analyze a resume against a job description using strict ATS rubric.
    
    Process:
    1. Extract JD keywords (must_have, good_to_have, domain)
    2. Score with strict rubric (temperature=0.0 for deterministic results)
    3. Apply Python-side hard caps
    4. Fallback if API unavailable
    """
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY is missing")
        return _fallback_response("AI analysis is currently unavailable")

    if not GROQ_CHAT_COMPLETIONS_URL:
        logger.error("GROQ_API_URL is missing")
        return _fallback_response("AI analysis is currently unavailable")

    if not resume_text.strip() or not jd_text.strip():
        return _fallback_response("Resume text or job description is empty")

    try:
        # Step 1: Extract JD keywords
        jd_info = await extract_jd_keywords(jd_text)
        logger.info(f"Extracted JD keywords: must_have={len(jd_info['must_have'])}, domain={jd_info['domain']}")
        
        # Step 2: Score with strict ATS rubric
        user_prompt = f"""
EXTRACTED JD REQUIREMENTS:
- Must-have skills: {jd_info.get('must_have', [])}
- Good-to-have: {jd_info.get('good_to_have', [])}
- Domain: {jd_info.get('domain', 'General')}

JOB DESCRIPTION:
{jd_text[:5000]}

RESUME:
{resume_text[:5000]}

Score strictly using the rubric. Apply all hard rules.

Return JSON format:
{{
  "final_score": <0-100>,
  "rating": "<Poor|Average|Good|Excellent>",
  "breakdown": {{
    "keyword_match": {{"score": <int>, "matched": [...], "missing": [...]}},
    "role_alignment": {{"score": <int>, "reason": "<str>"}},
    "skills_match": {{"score": <int>, "matched": [...], "missing": [...]}},
    "experience_match": {{"score": <int>, "required_years": <int>, "candidate_years": <int>}},
    "education": {{"score": <int>, "meets_requirement": <bool>}},
    "formatting": {{"score": <int>}}
  }},
  "suggestions": ["..."],
  "ai_feedback": "<2-3 sentences>"
}}
"""
        
        raw = await _call_groq_chat(
            user_prompt=user_prompt,
            system_prompt=STRICT_ATS_SYSTEM_PROMPT,
            max_tokens=2000,
        )
        parsed = _parse_json_response(raw)
        
        # Ensure expected structure for hard rules
        if "final_score" not in parsed:
            parsed["final_score"] = parsed.get("score", 0)
        if "breakdown" not in parsed:
            parsed["breakdown"] = {}
        if "flags" not in parsed:
            parsed["flags"] = []
        
        # Step 3: Apply Python-side hard caps
        result = apply_hard_rules(parsed, jd_info)
        
        # Map to legacy format for backward compatibility
        result["score"] = result.get("final_score", 0)
        result["matched_skills"] = result.get("breakdown", {}).get("skills_match", {}).get("matched", [])
        result["missing_skills"] = result.get("breakdown", {}).get("skills_match", {}).get("missing", [])
        result["suggestions"] = result.get("suggestions", [])
        
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