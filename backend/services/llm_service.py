"""
Groq-only LLM service for resume analysis.

Behavior:
- Uses Groq as the only remote AI provider.
- Falls back to a local ATS-style score calculator if Groq fails.
"""

import json
import logging
import os
import re
from collections import Counter
from typing import Any

import httpx
from dotenv import load_dotenv
from .keyword_utils import build_ngram_counter, extract_meaningful_terms, extract_skill_phrases
from .scoring_rules import (
    calculate_smart_score,
    detect_entry_level,
    detect_internship,
    detect_projects,
    extract_years_experience,
    calculate_education_score,
    calculate_required_years,
    apply_semantic_skill_matching,
)

load_dotenv()
logger = logging.getLogger(__name__)


# -- Provider configuration ----------------------------------------------------
def get_provider() -> str:
    """Return the active remote provider."""
    return "groq"


AI_PROVIDER = "groq"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192").strip() or "llama3-8b-8192"
GROQ_API_URL = (os.getenv("GROQ_API_URL", "https://api.groq.com").strip() or "https://api.groq.com").rstrip("/")
GROQ_CHAT_COMPLETIONS_URL = f"{GROQ_API_URL}/openai/v1/chat/completions"
GROQ_MODELS_URL = f"{GROQ_API_URL}/openai/v1/models"
GROQ_TIMEOUT = float(os.getenv("GROQ_TIMEOUT", "20"))


# -- Prompt --------------------------------------------------------------------
ATS_PROMPT = """Analyze this resume against the job description.

Return ONLY valid JSON (no markdown, no extra text):
{{
    "overall_score": <0-100 number with one decimal place, NEVER return exactly 50 or 85>,
    "skill_match": <0-100 number with one decimal place, NEVER return exactly 50 or 85>,
    "education_match": <0-100 number with one decimal place, NEVER return exactly 50 or 85>,
    "experience_match": <0-100 number with one decimal place, NEVER return exactly 50 or 85>,
    "missing_skills": ["skill1", "skill2", "skill3"],
    "education_gap": "<specific gap or 'None'>",
    "experience_gap": "<specific gap or 'None'>",
    "feedback": "<4-6 sentences of specific analysis>"
}}

JOB DESCRIPTION:
{job_description}

RESUME:
{resume_text}"""


# -- Local fallback scorer ------------------------------------------------------
def _sanitize_score(value: Any, fallback: float = 0.0) -> float:
    """Clamp to 0-100, keep one decimal place, and avoid reserved values."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = float(fallback)

    score = round(max(0.0, min(100.0, score)), 1)
    if score == 50.0:
        return 50.1
    if score == 85.0:
        return 84.9
    return score


def _extract_years(text: str) -> int | None:
    years = [
        int(match.group(1))
        for match in re.finditer(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)", text.lower())
    ]
    return max(years) if years else None


def _extract_experience_years_smart(resume_text: str, jd_text: str) -> float:
    """Smart experience extraction that intelligently handles entry-level candidates"""
    
    # Check if JD is entry-level
    entry_keywords = ["entry-level", "entry level", "fresher", "junior", 
                      "0-1", "0 to 1", "recent graduate", "0-2", "associate"]
    is_entry_level = any(kw in jd_text.lower() for kw in entry_keywords)
    
    # Extract standard years of experience first
    years_match = re.search(r'(\d+)\+?\s*(?:years?|yrs?)', resume_text.lower())
    base_years = float(years_match.group(1)) if years_match else 0.0
    
    if not is_entry_level:
        return base_years
    
    # For entry-level roles, also count internships and projects as experience
    # Extract internship duration (e.g., "6 months", "3 months", "6 week")
    internship_pattern = r'(?:intern(?:ship)?)[^.]*?(?:(\d+)\s*(?:months?|weeks?|years?))'
    internship_matches = re.findall(internship_pattern, resume_text.lower())
    
    internship_months = 0
    for match in internship_matches:
        if "week" in resume_text.lower()[resume_text.lower().find(match)-10:]:
            internship_months += int(match) / 4  # Convert weeks to months
        else:
            internship_months += int(match)
    
    # Count project mentions as proxy for practical experience
    # Each significant project section ≈ 0.5 months of learning
    project_count = len(re.findall(r'(?i)(?:project|built|developed|engineered|created)', resume_text))
    project_weight = min(6, project_count * 0.5)  # Cap at 6 months from projects
    
    # Calculate effective years for entry-level
    total_months = (base_years * 12) + internship_months + project_weight
    effective_years = total_months / 12
    
    # For entry-level, cap between 0.5 and 2 years equivalent experience
    return max(0.5, min(2.0, effective_years))


def calculate_local_score(job_description: str, resume_text: str) -> dict:
    """
    Calculate ATS-style local scores when Groq is unavailable, using intelligent dynamic scoring.
    
    This uses the same smart scoring rules as the AI system:
    - Entry-level detection
    - Weighted skill importance
    - Project/internship recognition
    - Education scoring
    - Semantic skill matching
    - Smart experience extraction (counts internships + projects for entry-level)
    """
    # Detect key factors first
    is_entry_level = detect_entry_level(job_description)
    has_internship = detect_internship(resume_text)
    has_projects = detect_projects(resume_text)
    
    # Use smart experience extraction that handles entry-level properly
    resume_years = _extract_experience_years_smart(resume_text, job_description)
    required_years = calculate_required_years(job_description)
    education_score = calculate_education_score(resume_text, job_description)
    
    # Extract terms and skills
    jd_terms = extract_meaningful_terms(job_description, min_len=3)
    resume_tokens = extract_meaningful_terms(resume_text, min_len=3)
    resume_terms = set(resume_tokens)

    # Extract phrase-based skills (better for compound skills like "machine learning", "rag pipeline")
    jd_phrases = extract_skill_phrases(job_description, min_terms=2, max_terms=3)
    resume_phrases = extract_skill_phrases(resume_text, min_terms=2, max_terms=3)
    
    jd_phrase_counter = Counter(jd_phrases) if jd_phrases else build_ngram_counter(jd_terms, (2, 3))
    resume_phrase_counter = Counter(resume_phrases) if resume_phrases else build_ngram_counter(resume_tokens, (2, 3))
    
    # Combine terms and phrases for comprehensive matching
    all_jd_skills = list(set(jd_terms + list(jd_phrase_counter.keys())))
    
    # Match skills - both terms and phrases
    matched_skills_raw = []
    for skill in all_jd_skills:
        skill_lower = skill.lower()
        # Check exact match
        if skill_lower in resume_terms or skill_lower in resume_phrase_counter:
            matched_skills_raw.append(skill)
        # Check substring match for phrases
        else:
            for resume_term in resume_terms:
                if skill_lower in resume_term or resume_term in skill_lower:
                    matched_skills_raw.append(skill)
                    break
    
    missing_skills_raw = [s for s in all_jd_skills if s not in matched_skills_raw]
    
    # Apply semantic matching to improve accuracy
    matched_skills, missing_skills = apply_semantic_skill_matching(
        matched_skills_raw, missing_skills_raw, job_description, resume_text
    )
    
    # Remove duplicates and limit
    matched_skills = list(set(matched_skills))[:15]
    missing_skills = list(set(missing_skills))[:10]
    
    # Use smart scoring system
    smart_score = calculate_smart_score(
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        is_entry_level=is_entry_level,
        resume_years=resume_years,
        required_years=required_years,
        has_internship=has_internship,
        has_projects=has_projects,
        education_score=education_score,
    )
    
    # Calculate baseline metrics
    jd_counter = Counter(jd_terms)
    weighted_total = sum(jd_counter.values())
    weighted_match = sum(weight for term, weight in jd_counter.items() if term in resume_terms)
    
    ranked_terms = sorted(jd_counter.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    priority_terms = [term for term, _count in ranked_terms[:20]]
    matched_priority_terms = [term for term in priority_terms if term in resume_terms]
    
    # Build comprehensive feedback
    feedback_parts = [
        f"Smart analysis scored {smart_score['score']}% based on {len(matched_skills)} matched skills",
        f"vs {len(missing_skills)} missing required skills.",
    ]
    
    if is_entry_level:
        feedback_parts.append(f"Entry-level role: projects and internships counted as valid experience.")
        feedback_parts.append(f"Effective experience: {resume_years:.1f} years (including internships/projects).")
    
    if has_projects:
        feedback_parts.append(f"Strong project experience adds bonus points.")
    
    if education_score > 0:
        feedback_parts.append(f"Quality education (+{education_score}pts) strengthens candidacy.")
    
    if len(matched_skills) >= len(missing_skills):
        feedback_parts.append(f"Matched skills exceed missing skills - good fit!")
    else:
        gap_count = len(missing_skills) - len(matched_skills)
        feedback_parts.append(f"Missing {gap_count} more skills than matched - potential gap.")
    
    feedback = " ".join(feedback_parts)[:900]
    
    # Build final response in the same format as LLM service
    return {
        "overall_score": smart_score["score"],
        "skill_match": smart_score["skill_score"],
        "education_match": min(100, (education_score * 5) + 50),  # Normalize to 0-100
        "experience_match": (
            100 if resume_years >= (required_years or 0) 
            else (resume_years / (required_years or 1)) * 100
        ) if required_years else 75,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "education_gap": "None" if education_score > 0 else "Limited education details",
        "experience_gap": (
            f"Entry-level: effective {resume_years:.1f} years (internships/projects included)"
            if is_entry_level
            else f"Requires {required_years}+ years; resume shows {resume_years} years"
        ) if required_years else "None",
        "feedback": feedback,
        "is_entry_level": is_entry_level,
        "has_projects": has_projects,
        "has_internship": has_internship,
        "reasoning": smart_score["reasoning"],
    }


# -- Groq call -----------------------------------------------------------------
def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text[:300] if response.text else "Unknown error"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
        if error:
            return str(error)
    return str(payload)[:300]


async def call_groq(prompt: str) -> str:
    """Call Groq chat completion endpoint and return raw message content."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON only. Do not include markdown.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.2,
        "max_tokens": 1800,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=GROQ_TIMEOUT) as client:
        response = await client.post(GROQ_CHAT_COMPLETIONS_URL, json=payload, headers=headers)

        # Some model/config combinations may reject response_format.
        if response.status_code == 400 and "response_format" in response.text.lower():
            payload.pop("response_format", None)
            response = await client.post(GROQ_CHAT_COMPLETIONS_URL, json=payload, headers=headers)

        if response.status_code >= 400:
            detail = _extract_error_message(response)
            raise RuntimeError(f"Groq API error ({response.status_code}): {detail}")

        body = response.json()

    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Groq response missing choices")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not content:
        raise RuntimeError("Groq response message is empty")

    return str(content)


# -- JSON parsing ---------------------------------------------------------------
def parse_llm_response(raw_text: str) -> dict:
    """Parse JSON from model response, including fenced code block content."""
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty LLM response")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "").strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("Could not parse LLM response as JSON")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON is not an object")
    return parsed


# Backward-compatible alias used by existing tests/debug snippets.
def _parse_llm_json(raw_text: str) -> dict:
    return parse_llm_response(raw_text)


def _normalize_result(candidate: dict, job_description: str, resume_text: str) -> dict:
    """Normalize and type-sanitize provider output."""
    baseline = calculate_local_score(job_description, resume_text)

    if not isinstance(candidate, dict):
        return baseline

    merged = {**baseline, **candidate}
    for key in ("overall_score", "skill_match", "education_match", "experience_match"):
        merged[key] = _sanitize_score(merged.get(key), baseline[key])

    missing_skills = merged.get("missing_skills")
    if not isinstance(missing_skills, list):
        merged["missing_skills"] = baseline["missing_skills"]
    else:
        merged["missing_skills"] = [str(skill)[:100] for skill in missing_skills[:10]]
        if not merged["missing_skills"]:
            merged["missing_skills"] = baseline["missing_skills"]

    for key in ("education_gap", "experience_gap", "feedback"):
        value = str(merged.get(key, baseline[key])).strip()
        merged[key] = value[:1200] if value else baseline[key]

    return merged


async def _run_provider(provider: str, prompt: str, job_description: str, resume_text: str) -> dict:
    if provider == "local":
        return calculate_local_score(job_description, resume_text)
    if provider == "groq":
        raw = await call_groq(prompt)
        return parse_llm_response(raw)
    raise ValueError(f"Unknown provider: {provider}")


# -- Public API ----------------------------------------------------------------
async def analyze_resume(
    job_description: str,
    resume_text: str,
    provider: str | None = None,
) -> dict:
    """Analyze resume text against job description text using Groq with local fallback."""
    if not (job_description or "").strip() or not (resume_text or "").strip():
        result = calculate_local_score(job_description or "", resume_text or "")
        result["feedback"] = "Resume or job description is empty."
        return result

    selected_provider = (provider or "groq").lower().strip()
    if selected_provider not in {"groq", "local"}:
        logger.warning("Unsupported provider override '%s', using groq", selected_provider)
        selected_provider = "groq"

    prompt = ATS_PROMPT.format(
        job_description=job_description[:7000],
        resume_text=resume_text[:7000],
    )

    try:
        raw_result = await _run_provider(selected_provider, prompt, job_description, resume_text)
        return _normalize_result(raw_result, job_description, resume_text)
    except Exception as exc:
        logger.error("Provider '%s' failed: %s", selected_provider, exc)
        fallback = calculate_local_score(job_description, resume_text)
        fallback["feedback"] = (
            f"{fallback['feedback']} Groq request failed, so local fallback scoring was used."
        )[:1200]
        return fallback


async def list_groq_models() -> list[str]:
    """List available Groq models for the configured API key."""
    if not GROQ_API_KEY:
        return []

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(GROQ_MODELS_URL, headers=headers)
            response.raise_for_status()
            payload = response.json()
        return [
            item["id"]
            for item in payload.get("data", [])
            if isinstance(item, dict) and "id" in item
        ]
    except Exception as exc:
        logger.warning("Failed to list Groq models: %s", exc)
        return []
