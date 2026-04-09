from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
import auth
import json
import uuid
import os
import aiofiles
import logging
import math
import re
import asyncio
from collections import Counter
from difflib import SequenceMatcher
try:
    from fuzzywuzzy import fuzz
    FUZZYWUZZY_AVAILABLE = True
except ImportError:
    FUZZYWUZZY_AVAILABLE = False
from services.file_parser import extract_text
from services.analyzer import calculate_dynamic_score, calculate_project_bonus
from services.groq_service import analyze_resume as analyze_resume_ai, refine_professional_skills
from services.jd_parser import (
    detect_job_level,
    adjust_score_by_level,
    calculate_experience_threshold,
    analyze_skill_emphasis,
)
from services.keyword_utils import DOMAIN_AGNOSTIC_STOPWORDS, extract_meaningful_terms, extract_skill_phrases

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])

# Use an absolute path so the directory is always resolved correctly,
# regardless of the working directory Render chooses at startup.
UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# The active AI provider — recorded on every submission for admin visibility
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")
MAX_OUTPUT_SKILLS = 15
AI_UNAVAILABLE_MESSAGE = "AI analysis unavailable, showing basic results"

# ── Skill Normalization Mapping (aliases → canonical form) ───────────────────
SKILL_NORMALIZATION_MAP = {
    "llm": "large language models",
    "llms": "large language models",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "sql": "sql",
    "nosql": "nosql databases",
    "rest": "rest apis",
    "api": "apis",
    "full stack": "full stack development",
    "devops": "devops",
    "ci/cd": "ci/cd pipelines",
    "qa": "quality assurance",
    "ui": "user interface design",
    "ux": "user experience design",
    "react": "react",
    "vue": "vue",
    "angular": "angular",
    "node": "node.js",
    "django": "django",
    "fastapi": "fastapi",
    "flask": "flask",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "aws": "aws",
    "gcp": "google cloud platform",
    "azure": "azure",
}

# ── PHASE 1: Invalid/Weak Skills (to be filtered out) ──────────────────────────
INVALID_SKILLS = {
    "software engineer",
    "software engineering",
    "software development",
    "application development",
    "real time",
    "real-time",
    "system",
    "systems",
    "process",
    "processes",
    "development",
    "engineering",
    "specialist",
    "professional",
    "expert",
    "support",
    "service",
    "services",
    "management",
    "manager",
    "analyst",
    "analysis",
    "business",
    "operations",
    "infrastructure",
    "platform",
    "framework",
}

# ── PHASE 4: High-Value Skills (weighted higher in scoring) ────────────────────
HIGH_VALUE_SKILLS = {
    "rag",
    "llm",
    "large language models",
    "fastapi",
    "react",
    "deep learning",
    "machine learning",
    "natural language processing",
    "nlp",
    "computer vision",
    "pytorch",
    "tensorflow",
    "kubernetes",
    "docker",
    "aws",
    "gcp",
    "azure",
    "gpu",
    "cuda",
    "distributed systems",
    "microservices",
    "devops",
}

_LOW_VALUE_SKILL_TOKENS = {
    "ability",
    "abilities",
    "candidate",
    "candidates",
    "experience",
    "experiences",
    "knowledge",
    "requirement",
    "requirements",
    "responsibility",
    "responsibilities",
    "role",
    "roles",
    "skill",
    "skills",
    "team",
    "work",
    "working",
}
_LOW_VALUE_SINGLE_SKILLS = {
    "analyst",
    "analysis",
    "developer",
    "developers",
    "development",
    "engineer",
    "engineers",
    "engineering",
    "management",
    "operation",
    "operations",
    "process",
    "processes",
    "reporting",
    "workflow",
    "workflows",
}

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: JD SECTION FILTER — Extract ONLY from skills sections
# ─────────────────────────────────────────────────────────────────────────────
JD_SECTION_KEYWORDS = {
    "skills", "technical skills", "requirements", "required skills",
    "technical requirements", "must have", "expected skills",
    "core skills", "key skills", "essential skills",
    "nice to have", "preferred skills", "proficiencies"
}

def _extract_jd_skills_section(jd_text: str) -> str:
    """
    FIX 1: Extract ONLY relevant JD sections.
    Filters out education, CGPA, certifications, responsibilities.
    Returns lines containing skill-related keywords.
    """
    jd_lower = (jd_text or "").lower()
    lines = jd_text.split("\n")
    relevant_lines = []
    in_skills_section = False
    
    for line in lines:
        line_lower = line.lower()
        
        # Start collecting if we hit a skills section
        if any(keyword in line_lower for keyword in JD_SECTION_KEYWORDS):
            in_skills_section = True
            relevant_lines.append(line)
            continue
        
        # Stop if we hit an education/requirements section
        if in_skills_section and any(
            keyword in line_lower 
            for keyword in ["education", "degree", "cgpa", "gpa", "qualification", "experience"]
        ):
            if not any(skill_keyword in line_lower for skill_keyword in ["experience in", "experience with"]):
                in_skills_section = False
        
        # Collect lines after skills keyword
        if in_skills_section:
            relevant_lines.append(line)
    
    return " ".join(relevant_lines) if relevant_lines else jd_text

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: HARD FILTER — Remove invalid terms
# ─────────────────────────────────────────────────────────────────────────────
INVALID_TERMS_IN_SKILLS = {
    "cgpa", "gpa", "education", "student", "currently",
    "pursuing", "degree", "certification", "certifications",
    "responsibilities", "requirements", "required",
    "bachelor", "master", "diploma", "phd", "college",
    "university", "institute", "school", "studying"
}

def _remove_invalid_skills(skills: list[str]) -> list[str]:
    """
    FIX 3: Hard filter invalid skills.
    Removes terms related to education, CGPA, certifications.
    """
    filtered = []
    for skill in skills:
        skill_lower = skill.lower().strip()
        
        # Skip if contains invalid terms
        if any(term in skill_lower for term in INVALID_TERMS_IN_SKILLS):
            continue
        
        # Skip single characters
        if len(skill_lower) < 2:
            continue
        
        filtered.append(skill)
    
    return filtered

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: GROUP SIMILAR SKILLS — Merge duplicates
# ─────────────────────────────────────────────────────────────────────────────
def _merge_similar_skills(skills: list[str]) -> list[str]:
    """
    FIX 4: Group and merge similar skills.
    Handles variations like:
    - 'rag pipeline', 'rag', 'retrieval augmented generation'
    - 'python', 'python3', 'py'
    """
    if not skills:
        return []
    
    merged = []
    used = set()
    
    for skill in skills:
        skill_norm = skill.lower().strip()
        
        # Skip if already grouped
        if skill_norm in used:
            continue
        
        # Find similar skills using advanced matching
        group = [skill_norm]
        for other_skill in skills:
            other_norm = other_skill.lower().strip()
            if other_norm in used or other_norm == skill_norm:
                continue
            
            # Check if similar using multiple strategies
            if _advanced_skill_match(skill_norm, other_norm):
                group.append(other_norm)
                used.add(other_norm)
        
        # Use longest skill name in group (most descriptive)
        best_skill = max(group, key=len)
        merged.append(best_skill)
        used.add(skill_norm)
    
    return merged

# ─────────────────────────────────────────────────────────────────────────────
# FIX 5: REMOVE LOW-VALUE MATCHES
# ─────────────────────────────────────────────────────────────────────────────
MIN_SKILL_LENGTH = 3

def _filter_short_skills(skills: list[str]) -> list[str]:
    """
    FIX 5: Remove very short/low-value skills.
    Filters out single letters and 2-letter acronyms.
    """
    return [s for s in skills if len(s.strip()) >= MIN_SKILL_LENGTH]


def _normalized_score_or_none(value: object) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(score):
        return None

    return round(max(0.0, min(100.0, score)), 1)


def _to_score(value: object, default: float = 0.0) -> float:
    parsed = _normalized_score_or_none(value)
    if parsed is not None:
        return parsed

    fallback = _normalized_score_or_none(default)
    return fallback if fallback is not None else 0.0


def _normalize_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = [str(item).strip() for item in value]
    return [item for item in normalized if item][:20]


def _dedupe_list(values: list[str], limit: int = 30) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", str(value).strip().lower())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
        if len(deduped) >= max(1, limit):
            break
    return deduped


def _normalize_skill_alias(skill: str) -> str:
    """Normalize skill aliases to canonical forms (e.g., 'ml' → 'machine learning')."""
    normalized = re.sub(r"\s+", " ", str(skill).strip().lower())
    return SKILL_NORMALIZATION_MAP.get(normalized, normalized)


def _fuzzy_match_skills(skill_a: str, skill_b: str, threshold: float = 0.75) -> bool:
    """Check if two skills match using fuzzy similarity."""
    ratio = SequenceMatcher(None, skill_a.lower(), skill_b.lower()).ratio()
    return ratio >= threshold


def _advanced_skill_match(skill_a: str, skill_b: str) -> bool:
    """
    PHASE 2: Advanced semantic matching with hybrid approach.
    Uses multiple matching strategies:
    1. Exact match
    2. Token sort (handles variations like "rag pipeline" vs "pipeline rag")
    3. Substring matching (handles "vision" in "computer vision")
    4. Fuzzy ratio (general similarity)
    """
    skill_a_norm = skill_a.lower().strip()
    skill_b_norm = skill_b.lower().strip()
    
    # Exact match
    if skill_a_norm == skill_b_norm:
        return True
    
    # Token-based fuzzy matching (if available)
    if FUZZYWUZZY_AVAILABLE:
        # Token sort ratio handles word order variations
        if fuzz.token_sort_ratio(skill_a_norm, skill_b_norm) > 85:
            return True
    
    # Substring matching (e.g., "vision" matches "computer vision")
    if len(skill_a_norm) > 4 and len(skill_b_norm) > 4:
        a_tokens = set(skill_a_norm.split())
        b_tokens = set(skill_b_norm.split())
        if a_tokens and b_tokens:
            overlap = len(a_tokens & b_tokens)
            total = max(len(a_tokens), len(b_tokens))
            if overlap / total > 0.6:
                return True
    
    # Fallback to basic similarity
    ratio = SequenceMatcher(None, skill_a_norm, skill_b_norm).ratio()
    return ratio >= 0.75


def _filter_invalid_skills(skills: list[str]) -> list[str]:
    """
    PHASE 1: Filter out weak/invalid skill names.
    Keeps only real skills, removes generic terms.
    """
    filtered = []
    for skill in skills:
        normalized = re.sub(r"\s+", " ", str(skill).strip().lower())
        
        # Skip if in invalid list
        if normalized in INVALID_SKILLS:
            continue
        
        # Skip very short skills
        if len(normalized) < 3:
            continue
        
        # Skip if only stopwords
        parts = normalized.split()
        if all(p in DOMAIN_AGNOSTIC_STOPWORDS for p in parts):
            continue
        
        filtered.append(normalized)
    
    return filtered


def _calculate_skill_weight(skill: str) -> float:
    """
    PHASE 4: Calculate weight for a skill.
    High-value skills get 2x weight.
    """
    normalized = re.sub(r"\s+", " ", str(skill).strip().lower())
    if normalized in HIGH_VALUE_SKILLS:
        return 2.0
    return 1.0


def _calculate_experience_score(resume_text: str) -> float:
    """
    PHASE 6: Calculate experience score from resume.
    Simple but effective: looks for project mentions and years.
    """
    resume_lower = (resume_text or "").lower()
    
    score = 60.0  # Base score
    
    # Bonus for projects
    if "project" in resume_lower:
        score += 10
    if "built" in resume_lower or "developed" in resume_lower:
        score += 5
    
    # Bonus for years of experience
    for word in resume_lower.split():
        try:
            years = int(word)
            if 0 < years <= 60:
                score += min(years / 2, 10)
                break
        except ValueError:
            pass
    
    return min(score, 100.0)


def _build_nlp_candidate_keywords(text: str, dedupe: bool = True) -> list[str]:
    terms = extract_meaningful_terms(text, min_len=3)
    phrases = extract_skill_phrases(text, min_terms=2, max_terms=3)
    combined = [
        re.sub(r"\s+", " ", str(item).strip().lower())
        for item in (phrases + terms)
        if str(item).strip()
    ]
    if dedupe:
        return _dedupe_list(combined, limit=80)
    return combined


def _normalize_text_for_skill_validation(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _count_skill_occurrences(skill: str, normalized_text: str) -> int:
    normalized_skill = re.sub(r"\s+", " ", str(skill).strip().lower())
    if not normalized_skill or not normalized_text:
        return 0
    pattern = r"\b" + re.escape(normalized_skill).replace(r"\ ", r"\s+") + r"\b"
    return len(re.findall(pattern, normalized_text))


def _is_validated_skill(skill: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(skill).strip().lower())
    if not normalized or len(normalized) < 2 or normalized.isdigit():
        return False

    parts = normalized.split()
    if not parts:
        return False

    if all(part in DOMAIN_AGNOSTIC_STOPWORDS for part in parts):
        return False

    if len(parts) == 1:
        token = parts[0]
        if token in DOMAIN_AGNOSTIC_STOPWORDS or token in _LOW_VALUE_SKILL_TOKENS:
            return False
        if token in _LOW_VALUE_SINGLE_SKILLS:
            return False

    if parts[-1] in _LOW_VALUE_SKILL_TOKENS:
        return False

    return True


def _rank_validated_skills(
    refined_skills: list[str],
    raw_candidates: list[str],
    source_text: str,
    limit: int = MAX_OUTPUT_SKILLS,
) -> list[str]:
    normalized_refined = _dedupe_list(refined_skills, limit=80)
    candidate_counts: Counter[str] = Counter(
        re.sub(r"\s+", " ", str(item).strip().lower())
        for item in raw_candidates
        if str(item).strip()
    )
    normalized_text = _normalize_text_for_skill_validation(source_text)
    phrase_tokens = {
        token
        for skill in normalized_refined
        if " " in skill
        for token in skill.split()
    }

    ranked: list[tuple[str, float, int, int]] = []
    for skill in normalized_refined:
        if not _is_validated_skill(skill):
            continue

        skill_parts = skill.split()
        if len(skill_parts) == 1 and skill_parts[0] in phrase_tokens:
            continue

        phrase_frequency = candidate_counts.get(skill, 0)
        token_frequency = sum(candidate_counts.get(token, 0) for token in skill_parts)
        text_frequency = _count_skill_occurrences(skill, normalized_text)

        # Keep only grounded skills to avoid noisy/hallucinated output.
        if phrase_frequency == 0 and token_frequency == 0 and text_frequency == 0:
            continue

        importance = (phrase_frequency * 4.0) + (text_frequency * 3.0) + float(token_frequency)
        if len(skill_parts) > 1:
            importance += 2.0
        importance += min(len(skill_parts), 3)

        ranked.append((skill, importance, phrase_frequency, text_frequency))

    ranked.sort(key=lambda item: (-item[1], -item[2], -item[3], item[0]))
    return [skill for skill, _importance, _p_freq, _t_freq in ranked[: max(1, limit)]]


async def _extract_refined_skills(text: str, limit: int = MAX_OUTPUT_SKILLS) -> list[str]:
    raw_candidates = _build_nlp_candidate_keywords(text, dedupe=False)
    if not raw_candidates:
        return []

    candidates = _dedupe_list(raw_candidates, limit=80)
    refined = await refine_professional_skills(candidates)
    return _rank_validated_skills(refined, raw_candidates, text, limit=limit)


def _extract_nlp_filtered_skills(text: str, limit: int = MAX_OUTPUT_SKILLS) -> list[str]:
    """Extract clean skills from NLP pipeline only (no AI refinement)."""
    raw_candidates = _build_nlp_candidate_keywords(text, dedupe=False)
    if not raw_candidates:
        return []

    filtered_candidates = _dedupe_list(raw_candidates, limit=80)
    return _rank_validated_skills(filtered_candidates, raw_candidates, text, limit=limit)


def _match_jd_resume_skills(
    jd_skills: list[str],
    resume_skills: list[str],
    limit: int = MAX_OUTPUT_SKILLS,
) -> tuple[list[str], list[str]]:
    """
    PHASE 2-3: Advanced skill matching with semantic understanding.
    - Uses advanced semantic matching (not just fuzzy)
    - Filters invalid/weak skills (PHASE 1)
    - Removes false missing skills (PHASE 3)
    - Sorts by importance (PHASE 7)
    """
    # PHASE 1: Filter out invalid weak skills
    filtered_jd = _filter_invalid_skills(jd_skills)
    filtered_resume = _filter_invalid_skills(resume_skills)
    
    normalized_jd_skills = _dedupe_list(filtered_jd, limit=80)
    normalized_resume_skills = _dedupe_list(filtered_resume, limit=80)
    
    # Normalize skill aliases
    normalized_jd_skills = [_normalize_skill_alias(s) for s in normalized_jd_skills]
    normalized_resume_skills = [_normalize_skill_alias(s) for s in normalized_resume_skills]

    matched: list[str] = []
    missing: list[str] = []
    
    for jd_skill in normalized_jd_skills:
        found = False
        
        # Try advanced matching with multiple strategies
        for resume_skill in normalized_resume_skills:
            if _advanced_skill_match(jd_skill, resume_skill):
                found = True
                break
        
        if found:
            matched.append(jd_skill)
        else:
            missing.append(jd_skill)

    # PHASE 3: Remove false missing skills (items already in matched)
    missing = [m for m in missing if m not in matched]
    
    # PHASE 7: Sort by importance (high-value skills first, then by frequency)
    matched.sort(key=lambda x: _calculate_skill_weight(x), reverse=True)
    missing.sort(key=lambda x: _calculate_skill_weight(x), reverse=True)
    
    # PHASE 7: Limit output to 8 skills each
    return matched[:8], missing[:8]


def _is_ai_unavailable(ai_result: dict | None) -> bool:
    if not isinstance(ai_result, dict):
        return True

    ai_score = _normalized_score_or_none(ai_result.get("score"))
    if ai_score is None:
        return True

    suggestions = _normalize_list(ai_result.get("suggestions"))
    suggestion_text = " ".join(suggestions).lower()
    fallback_markers = (
        "not configured",
        "request timed out",
        "request failed",
        "temporarily unavailable",
        "unexpected error",
        "api key",
        "api url",
    )
    if any(marker in suggestion_text for marker in fallback_markers):
        return True

    matched = _normalize_list(ai_result.get("matched_skills"))
    missing = _normalize_list(ai_result.get("missing_skills"))
    if ai_score == 0.0 and not matched and not missing:
        return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# NEW SCORING FUNCTIONS (5 CRITICAL FIXES)
# ═══════════════════════════════════════════════════════════════════════════════

def _deduplicate_skills(skills: list[str]) -> list[str]:
    """
    FIX 5: Remove duplicate JD terms and return deduplicated list.
    Preserves order while removing duplicates.
    """
    seen = set()
    result = []
    for skill in skills:
        normalized = re.sub(r"\s+", " ", str(skill).strip().lower())
        if normalized not in seen:
            seen.add(normalized)
            result.append(skill)
    return result


def _limit_jd_skills(skills: list[str], limit: int = 15) -> list[str]:
    """
    FIX 1: Limit JD skills to top N important ones.
    Reduces inflated denominator that kills scores.
    """
    if len(skills) <= limit:
        return skills
    
    # Sort by skill weight (HIGH_VALUE_SKILLS float to top)
    sorted_skills = sorted(
        skills,
        key=lambda s: (_calculate_skill_weight(s), len(s)),
        reverse=True
    )
    return sorted_skills[:limit]


def _weighted_skill_score(matched_skills: list[str], jd_skills: list[str]) -> float:
    """
    FIX 2: Calculate weighted skill match percentage.
    HIGH_VALUE_SKILLS get 2x weight, others get 1x.
    Returns percentage 0-100.
    """
    if not jd_skills:
        return 0.0
    
    matched_weight = sum(_calculate_skill_weight(s) for s in matched_skills)
    total_weight = sum(_calculate_skill_weight(s) for s in jd_skills)
    
    if total_weight == 0:
        return 0.0
    
    return round((matched_weight / total_weight) * 100, 1)


def _bonus_boost(score: float, matched_skills: list[str]) -> float:
    """
    FIX 3: Apply bonus boost for core AI/ML skills.
    If 3+ core skills match: +5 points
    If 2+ core skills match: +3 points
    """
    CORE_SKILLS = {
        "rag",
        "llm",
        "large language models",
        "machine learning",
        "deep learning",
        "pytorch",
        "tensorflow",
        "huggingface",
    }
    
    matched_lower = set(re.sub(r"\s+", " ", s.strip().lower()) for s in matched_skills)
    core_hits = sum(1 for skill in CORE_SKILLS if skill in matched_lower)
    
    bonus = 0
    if core_hits >= 3:
        bonus = 5
    elif core_hits >= 2:
        bonus = 3
    
    return min(score + bonus, 100.0)


@router.post("", response_model=schemas.AnalyzeResponse)
async def analyze(
    resume: UploadFile = File(...),
    jd_text: str = Form(None),
    jd_file: UploadFile = File(None),
    job_template_id: int = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_user),
):
    """
    Analyze a resume against a job description.

    Exactly one of the following must be provided:
      - job_template_id  (uses a saved template's JD)
      - jd_text          (raw text pasted by the user)
      - jd_file          (uploaded JD file)
    """
    logger.info(f"Analyze request: user={current_user.id}, template_id={job_template_id}")

    # ── Resolve job description ────────────────────────────────────────────────
    job_template = None
    if job_template_id:
        job_template = db.query(models.JobTemplate).filter(
            models.JobTemplate.id == job_template_id
        ).first()
        if not job_template:
            raise HTTPException(status_code=404, detail="Job template not found")
        job_description = job_template.description
        logger.info(f"Using job template {job_template_id}: {len(job_description)} chars")

    elif jd_text and jd_text.strip():
        job_description = jd_text.strip()
        logger.info(f"Using jd_text: {len(job_description)} chars")

    elif jd_file:
        jd_bytes = await jd_file.read()
        if len(jd_bytes) == 0:
            raise HTTPException(status_code=400, detail="Job description file is empty")
        try:
            job_description = extract_text(jd_file.filename, jd_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    else:
        raise HTTPException(
            status_code=400,
            detail="Provide a job description as text, file, or select a job template",
        )

    if not job_description or len(job_description.strip()) < 10:
        raise HTTPException(status_code=400, detail="Job description is too short (min 10 chars)")

    # ── Read resume bytes ──────────────────────────────────────────────────────
    resume_bytes = await resume.read()
    logger.info(f"Resume: {resume.filename} ({len(resume_bytes)} bytes)")

    if len(resume_bytes) == 0:
        raise HTTPException(status_code=400, detail="Resume file is empty")

    # ── 1) Extract resume text ─────────────────────────────────────────────────
    try:
        resume_text = extract_text(resume.filename, resume_bytes)
    except ValueError as e:
        logger.error(f"Resume parsing failed: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse resume: {str(e)}")

    if not resume_text or len(resume_text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Could not extract sufficient text from resume")

    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 1: FILTER JD TO SKILLS SECTION ONLY (most important!)
    # ═══════════════════════════════════════════════════════════════════════════
    job_description_filtered = _extract_jd_skills_section(job_description)
    logger.info(f"JD filtered from {len(job_description)} → {len(job_description_filtered)} chars")

    # ── Extract skills using filtered JD ──────────────────────────────────────
    jd_skills, resume_skills = await asyncio.gather(
        _extract_refined_skills(job_description_filtered, limit=MAX_OUTPUT_SKILLS),
        _extract_refined_skills(resume_text, limit=MAX_OUTPUT_SKILLS),
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 3 + 4 + 5: APPLY HARD FILTERS, MERGE, AND LENGTH FILTER
    # ═══════════════════════════════════════════════════════════════════════════
    jd_skills = _remove_invalid_skills(jd_skills)           # FIX 3: Remove CGPA, education, etc.
    jd_skills = _merge_similar_skills(jd_skills)             # FIX 4: Merge duplicates
    jd_skills = _filter_short_skills(jd_skills)              # FIX 5: Remove short skills
    
    resume_skills = _remove_invalid_skills(resume_skills)    # FIX 3
    resume_skills = _merge_similar_skills(resume_skills)     # FIX 4
    resume_skills = _filter_short_skills(resume_skills)      # FIX 5
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW SCORING FIXES: FIX 1 (limit) + FIX 5 (deduplicate)
    # ═══════════════════════════════════════════════════════════════════════════
    jd_skills = _deduplicate_skills(jd_skills)              # FIX 5: Remove duplicates
    jd_skills = _limit_jd_skills(jd_skills, limit=15)       # FIX 1: Limit to top 15
    
    logger.info(f"After filtering: JD skills={len(jd_skills)}, Resume skills={len(resume_skills)}")
    
    # ── 2) Compute keyword score (existing logic) ─────────────────────────────
    keyword_result = calculate_dynamic_score(resume_text, job_description)
    if not isinstance(keyword_result, dict):
        logger.warning("Keyword analyzer returned invalid payload type: %s", type(keyword_result).__name__)
        keyword_result = {}
    keyword_score = _to_score(keyword_result.get("overall_score", 0))

    # ── 3) Call Groq AI service ───────────────────────────────────────────────
    ai_result = None
    ai_unavailable = False
    try:
        ai_result = await analyze_resume_ai(resume_text=resume_text, jd_text=job_description_filtered)
        ai_unavailable = _is_ai_unavailable(ai_result)
    except Exception as e:
        logger.error(f"Groq analysis failed: {e}")
        ai_unavailable = True
        ai_result = None

    # ── 4) Extract AI score and combine ───────────────────────────────────────
    ai_score = 0.0
    if not ai_unavailable:
        ai_score_candidate = _normalized_score_or_none((ai_result or {}).get("score"))
        if ai_score_candidate is None:
            ai_unavailable = True
        else:
            ai_score = ai_score_candidate

    if ai_unavailable:
        # AI failed: force NLP-only skills so output remains clean and deterministic.
        jd_skills_filtered = _extract_nlp_filtered_skills(job_description_filtered, limit=MAX_OUTPUT_SKILLS)
        resume_skills_filtered = _extract_nlp_filtered_skills(resume_text, limit=MAX_OUTPUT_SKILLS)
        jd_skills = _remove_invalid_skills(jd_skills_filtered)
        resume_skills = _remove_invalid_skills(resume_skills_filtered)

    matched_skills, missing_skills = _match_jd_resume_skills(
        jd_skills,
        resume_skills,
        limit=MAX_OUTPUT_SKILLS,
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 2: AI AS FINAL AUTHORITY — Override rule-based with AI results
    # ═══════════════════════════════════════════════════════════════════════════
    if not ai_unavailable and ai_result:
        ai_matched = _normalize_list(ai_result.get("matched_skills", []))
        ai_missing = _normalize_list(ai_result.get("missing_skills", []))
        
        # Use AI results if they exist and are reasonable
        if ai_matched or ai_missing:
            logger.info(f"Using AI results: matched={len(ai_matched)}, missing={len(ai_missing)}")
            # Apply same filtering to AI results for consistency
            ai_matched = _remove_invalid_skills(ai_matched)
            ai_missing = _remove_invalid_skills(ai_missing)
            ai_matched = _merge_similar_skills(ai_matched)
            ai_missing = _merge_similar_skills(ai_missing)
            ai_matched = _filter_short_skills(ai_matched)[:8]
            ai_missing = _filter_short_skills(ai_missing)[:8]
            
            # Override rule-based with AI results (FIX 2)
            matched_skills = ai_matched
            missing_skills = ai_missing
            logger.info(f"After AI override: matched={len(matched_skills)}, missing={len(missing_skills)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 4-6: Advanced Scoring with Weighting & AI Validation
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Calculate weighted skill match
    total_jd_skills = max(len(jd_skills), 1)
    
    # PHASE 4: Calculate weighted match percentage
    matched_weight = sum(_calculate_skill_weight(s) for s in matched_skills)
    total_weight = sum(_calculate_skill_weight(s) for s in jd_skills)
    if total_weight > 0:
        weighted_skill_match = round((matched_weight / total_weight) * 100, 1)
    else:
        weighted_skill_match = 0.0
    
    # PHASE 6: Calculate experience score
    experience_score = _calculate_experience_score(resume_text)
    
    # PHASE 5: AI Confidence Check
    # If AI result has very few matched skills, fall back to rule-based
    ai_matched_skills = len(matched_skills)
    use_rule_based = ai_unavailable or ai_matched_skills < 2
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW SCORING FIXES: FIX 2 (weighted) + FIX 3 (bonus) + FIX 4 (calibration)
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Base score: FIX 2 - Use weighted skill score as primary driver
    skill_score_weighted = _weighted_skill_score(matched_skills, jd_skills)
    
    # Apply FIX 3 - Bonus boost for core AI/ML skills
    skill_score_boosted = _bonus_boost(skill_score_weighted, matched_skills)
    
    # FIX 4: Final Score Calibration
    # Use boosted skill score (60%) + AI (25%) + keyword (15%) when AI available
    # This makes matching quality the PRIMARY driver
    if ai_unavailable or use_rule_based:
        # Rule-based: skill match (60%) + experience (40%)
        final_score = round(
            (0.6 * skill_score_boosted) + (0.4 * experience_score),
            1
        )
        logger.info(f"Using rule-based scoring: skill={skill_score_boosted}, exp={experience_score}, final={final_score}")
    else:
        # AI-assisted: skill match (60%) + AI (25%) + keyword (15%)
        # This incentivizes strong matching while respecting AI confidence
        final_score = round(
            (0.6 * skill_score_boosted) + (0.25 * ai_score) + (0.15 * keyword_score),
            1
        )
        logger.info(f"Using AI-assisted scoring: skill={skill_score_boosted}, ai={ai_score}, kw={keyword_score}, final={final_score}")

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW INTELLIGENT SCORING: Job Level Detection & Bonuses
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Detect job level (entry-level, mid, senior)
    jd_level = detect_job_level(job_description)
    logger.info(f"📋 Job Level: {jd_level['level'].upper()} (friendly={jd_level['is_entry_level_friendly']})")
    
    # Detect internship and projects in resume
    has_internship = bool(re.search(r'(?i)intern(?:ship)?', resume_text))
    has_projects = bool(re.search(r'(?i)(?:project|built|developed|engineered)', resume_text))
    
    logger.info(f"   Resume: internship={has_internship}, projects={has_projects}")
    
    # Calculate project bonus
    project_bonus_info = calculate_project_bonus(resume_text, job_description)
    project_bonus = project_bonus_info.get("bonus_points", 0)
    
    logger.info(f"   Project Bonus: {project_bonus}pts ({project_bonus_info['relevant_projects']} relevant projects)")
    
    # Adjust score based on job level
    level_adjusted_score, level_adjustment_reason = adjust_score_by_level(
        int(final_score),
        jd_level,
        has_internship,
        has_projects
    )
    
    logger.info(f"   Level Adjustment: {level_adjusted_score - int(final_score):+d}pts ({level_adjustment_reason[:80]}...)")
    
    # Apply all bonuses
    final_score_with_bonuses = min(100, level_adjusted_score + project_bonus)
    bonus_applied = final_score_with_bonuses - final_score
    
    if bonus_applied > 0:
        logger.info(f"✨ Final Score Boosted: {final_score} → {final_score_with_bonuses} (+{bonus_applied} bonus)")
        final_score = final_score_with_bonuses
    
    suggestions = _normalize_list((ai_result or {}).get("suggestions"))
    if ai_unavailable:
        suggestions = [AI_UNAVAILABLE_MESSAGE]
    
    # Add job level info to suggestions/feedback
    if jd_level["is_entry_level_friendly"]:
        if bonus_applied > 0:
            suggestions.insert(0, f"Entry-level role: internships/projects counted as valid experience (+{project_bonus}pts)")
    elif jd_level["level"] == "senior":
        exp_threshold = calculate_experience_threshold(job_description)
        if exp_threshold["required_years"] and exp_threshold["required_years"] > 5:
            suggestions.insert(0, f"Senior role: expects {exp_threshold['required_years']}+ years of experience")
    if ai_unavailable:
        suggestions = [AI_UNAVAILABLE_MESSAGE]

    feedback = str(keyword_result.get("feedback", "")).strip()
    if suggestions:
        feedback = (feedback + " Suggestions: " + "; ".join(suggestions))[:1200]

    # ── Save resume file ───────────────────────────────────────────────────────
    ext = os.path.splitext(resume.filename)[1]
    saved_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, saved_filename)
    try:
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(resume_bytes)
        logger.info(f"Resume saved: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save resume file: {e}")
        # Non-fatal — analysis result is still returned

    # ── Persist submission ─────────────────────────────────────────────────────
    submission = models.Submission(
        user_id=current_user.id,
        job_template_id=job_template.id if job_template else None,
        jd_text=job_description,
        resume_filename=saved_filename,
        ats_score=final_score,
        skill_match=_to_score(keyword_result.get("skill_match", keyword_score), keyword_score),
        education_match=_to_score(keyword_result.get("education_match", 0), 0),
        experience_match=_to_score(keyword_result.get("experience_match", 0), 0),
        missing_skills=json.dumps(missing_skills),
        education_gap=str(keyword_result.get("education_gap", "")),
        experience_gap=str(keyword_result.get("experience_gap", "")),
        feedback=feedback,
        status="pending",
        llm_provider=AI_PROVIDER if not ai_unavailable else "keyword-fallback",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    logger.info(
        "Submission saved: ID=%s, Final Score=%s, Keyword Score=%s, AI Score=%s, AI Unavailable=%s",
        submission.id,
        final_score,
        keyword_score,
        ai_score,
        ai_unavailable,
    )

    return schemas.AnalyzeResponse(
        final_score=final_score,
        keyword_score=keyword_score,
        ai_score=ai_score,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        cleaned_skills=jd_skills,
        suggestions=suggestions,
        ai_unavailable=ai_unavailable,
        submission_id=submission.id,
        ats_score=final_score,
        skill_match=submission.skill_match,
        education_match=submission.education_match,
        experience_match=submission.experience_match,
        education_gap=submission.education_gap,
        experience_gap=submission.experience_gap,
        feedback=submission.feedback,
    )


@router.get("/history", response_model=list[schemas.SubmissionOut])
def history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_user),
):
    submissions = (
        db.query(models.Submission)
        .filter(models.Submission.user_id == current_user.id)
        .order_by(models.Submission.created_at.desc())
        .all()
    )
    return submissions


@router.get("/job-templates", response_model=list[schemas.JobTemplateOut])
def get_job_templates(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_user),
):
    """List all available job templates (accessible to any authenticated user)."""
    logger.info(f"User {current_user.id} listing job templates")
    return (
        db.query(models.JobTemplate)
        .order_by(models.JobTemplate.created_at.desc())
        .all()
    )
