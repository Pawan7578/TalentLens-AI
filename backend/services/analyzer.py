"""
ATS Analysis Service

Handles the core logic for analyzing resumes against job descriptions.
Orchestrates file parsing, LLM calls, and response formatting.
"""

import logging
from typing import Optional
from .file_parser import extract_text
from .llm_service import analyze_resume as call_llm

logger = logging.getLogger(__name__)


async def analyze_resume_vs_jd(
    resume_bytes: bytes,
    resume_filename: str,
    jd_text: str,
    provider: Optional[str] = None,
) -> dict:
    """
    Complete analysis pipeline: extract → analyze → structure response.

    Args:
        resume_bytes: Raw resume file bytes
        resume_filename: Resume filename (used for extension detection)
        jd_text: Job description text
        provider: LLM provider ("ollama" | "groq" | None)

    Returns:
        Structured response with scores and gaps:
        {
            "overall_score": int,
            "skill_match": int,
            "education_match": int,
            "experience_match": int,
            "missing_skills": list[str],
            "education_gap": str,
            "experience_gap": str,
            "feedback": str
        }

    Raises:
        ValueError: If file parsing fails or input is invalid
    """
    logger.info(f"Starting analysis: {resume_filename} vs JD")

    # Validate inputs
    if not resume_bytes or len(resume_bytes) == 0:
        logger.error("Resume file is empty")
        raise ValueError("Resume file is empty")

    if not jd_text or len(jd_text.strip()) < 10:
        logger.error("Job description is too short")
        raise ValueError("Job description must be at least 10 characters")

    # Extract resume text
    logger.info(f"Extracting text from resume: {resume_filename}")
    try:
        resume_text = extract_text(resume_filename, resume_bytes)
    except ValueError as e:
        logger.error(f"Resume extraction failed: {e}")
        raise ValueError(f"Failed to parse resume: {str(e)}")

    if not resume_text or len(resume_text.strip()) < 10:
        logger.error(f"Resume extraction yielded < 10 chars: {len(resume_text)}")
        raise ValueError("Could not extract sufficient text from resume")

    logger.info(f"Resume text extracted: {len(resume_text)} chars")
    logger.info(f"JD text provided: {len(jd_text)} chars")

    # Call LLM for analysis
    logger.info("Calling LLM service for analysis")
    try:
        result = await call_llm(jd_text, resume_text, provider=provider)

        # Ensure required fields exist
        if not result:
            logger.warning("LLM returned empty result, using defaults")
            result = _get_default_response()

        # Validate response structure
        result = _ensure_response_structure(result)
        logger.info(f"Analysis complete: score={result.get('overall_score')}")
        return result

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        # Return default response instead of failing completely
        return _get_default_response(
            feedback=f"Analysis error (using defaults): {str(e)[:100]}"
        )


def _get_default_response(feedback: str = None) -> dict:
    """Return a default structured response when LLM fails."""
    return {
        "overall_score": 50,
        "skill_match": 50,
        "education_match": 50,
        "experience_match": 50,
        "missing_skills": ["Unable to analyze"],
        "education_gap": "Unable to assess",
        "experience_gap": "Unable to assess",
        "feedback": feedback or "Analysis service temporarily unavailable.",
    }


def _ensure_response_structure(response: dict) -> dict:
    """Ensure response has all required fields with proper types."""
    defaults = {
        "overall_score": 50,
        "skill_match": 50,
        "education_match": 50,
        "experience_match": 50,
        "missing_skills": [],
        "education_gap": "Unknown",
        "experience_gap": "Unknown",
        "feedback": "Analysis complete.",
    }

    # Copy defaults and override with provided values
    result = defaults.copy()
    if not response:
        return result

    # Override with provided values, converting types as needed
    for key in defaults:
        if key in response:
            val = response[key]
            if key.endswith("_score") and isinstance(val, (int, float)):
                # Clamp scores to 0-100
                result[key] = max(0, min(100, int(val)))
            elif key == "missing_skills" and isinstance(val, list):
                result[key] = [str(s)[:100] for s in val[:10]]  # Max 10 skills, 100 chars each
            elif key in ("education_gap", "experience_gap", "feedback") and isinstance(val, str):
                result[key] = val[:500]  # Max 500 chars
            else:
                result[key] = val

    return result
