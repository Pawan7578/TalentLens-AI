"""
Dynamic ATS scoring rules that work for ANY JD/Resume pair.

This module provides intelligent, context-aware scoring that:
- Detects entry-level roles dynamically
- Assigns skill weights based on JD emphasis
- Recognizes projects and internships as valid experience
- Applies semantic skill matching
"""

import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


# -- High-value technical skills (3x weight when matched) --
HIGH_VALUE_SKILLS = {
    "python", "java", "javascript", "typescript", "rust", "golang", "go",
    "pytorch", "tensorflow", "keras", "fastapi", "django", "flask",
    "react", "vue", "angular", "nodejs", "node.js",
    "sql", "postgresql", "mysql", "mongodb", "redis",
    "aws", "azure", "gcp", "cloud",
    "docker", "kubernetes", "ci/cd", "cicd",
    "llm", "llms", "groq", "openai", "anthropic", "claude", "gpt",
    "rag", "retrieval-augmented generation", "embedding",
    "bert", "gpt-2", "llama", "mistral", "mixtral",
    "langchain", "chainlit", "huggingface",
    "git", "github", "gitlab", "bitbucket",
    "rest api", "graphql", "websocket",
    "machine learning", "ml", "deep learning", "nlp", "cv", "computer vision",
    "data science", "pandas", "numpy", "scikit-learn",
    "linux", "bash", "shell", "devops",
    "authentication", "oauth", "jwt", "bcrypt",
    "agile", "agile development", "scrum",
}

# Medium-value skills (2x weight)
MEDIUM_VALUE_SKILLS = {
    "figma", "adobe xd", "ui/ux", "ux design",
    "excel", "google sheets",
    "jira", "confluence",
    "testing", "pytest", "jest", "unittest",
    "html", "css", "sass", "tailwind",
    "json", "yaml", "xml",
    "api", "rest",
    "database", "db",
    "frontend", "backend", "fullstack",
    "responsive design",
}

# Low-value skills (1x weight) - these get penalized if missing
LOW_VALUE_SKILLS = {
    "power apps", "power bi", "php",
    "microsoft office",
}

ENTRY_LEVEL_KEYWORDS = {
    "entry-level", "entry level", "entry_level",
    "fresher", "fresh graduate",
    "junior", "jr.",
    "0-1", "0-2", "0 years", "entry position",
    "recent graduate", "graduate",
    "first time", "first job", "first role",
}


def _extract_skill_mentions(text: str, skill: str) -> int:
    """Count mentions of a skill in text (case-insensitive)."""
    if not text or not skill:
        return 0
    pattern = r"\b" + re.escape(skill.lower()) + r"\b"
    return len(re.findall(pattern, text.lower()))


def _get_skill_weight(skill: str) -> int:
    """Determine skill weight: 3=high, 2=medium, 1=low."""
    skill_lower = skill.lower().strip()
    
    if skill_lower in HIGH_VALUE_SKILLS:
        return 3
    if skill_lower in MEDIUM_VALUE_SKILLS:
        return 2
    if skill_lower in LOW_VALUE_SKILLS:
        return 1
    
    # Dynamic detection for compound skills
    if any(term in skill_lower for term in ["machine learning", "deep learning", "nlp", "rag", "llm"]):
        return 3
    if any(term in skill_lower for term in ["framework", "library", "api"]):
        return 2
    
    return 1


def detect_entry_level(jd_text: str) -> bool:
    """Check if JD is for an entry-level position."""
    if not jd_text:
        return False
    jd_lower = jd_text.lower()
    return any(keyword in jd_lower for keyword in ENTRY_LEVEL_KEYWORDS)


def detect_internship(resume_text: str) -> bool:
    """Check if resume mentions internship."""
    if not resume_text:
        return False
    resume_lower = resume_text.lower()
    return "intern" in resume_lower or "internship" in resume_lower


def detect_projects(resume_text: str) -> bool:
    """Check if resume has project section."""
    if not resume_text:
        return False
    resume_lower = resume_text.lower()
    return "project" in resume_lower


def extract_years_experience(resume_text: str) -> float:
    """Extract years of experience from resume."""
    if not resume_text:
        return 0.0
    
    # Look for patterns like "3 years", "3+ years", "3yrs"
    matches = re.findall(r"(\d+)\s*\+?\s*(?:years?|yrs?)", resume_text.lower())
    if matches:
        return float(max(int(m) for m in matches))
    return 0.0


def calculate_education_score(resume_text: str, jd_text: str) -> int:
    """Calculate education bonus: 0-20 points."""
    resume_lower = resume_text.lower()
    
    # Detect resume education level
    resume_edu_level = 0
    if "phd" in resume_lower or "doctorate" in resume_lower:
        resume_edu_level = 4
    elif "master" in resume_lower or "mba" in resume_lower:
        resume_edu_level = 3
    elif "btech" in resume_lower or "bca" in resume_lower or "mca" in resume_lower or "bachelor" in resume_lower:
        resume_edu_level = 2
    elif "diploma" in resume_lower or "associate" in resume_lower:
        resume_edu_level = 1
    
    if resume_edu_level == 0:
        return 0
    
    # Detect JD education requirement
    jd_lower = jd_text.lower()
    jd_edu_level = 0
    if "phd" in jd_lower or "doctorate" in jd_lower:
        jd_edu_level = 4
    elif "master" in jd_lower or "mba" in jd_lower:
        jd_edu_level = 3
    elif "bachelor" in jd_lower or "btech" in jd_lower:
        jd_edu_level = 2
    
    if jd_edu_level == 0:
        # No specific education requirement, give bonus for having any degree
        return 5 if resume_edu_level >= 2 else 0
    
    # Check for high CGPA
    cgpa_matches = re.findall(r"(\d\.\d)(?:/10|/4)?", resume_text)
    cgpa_bonus = 0
    if cgpa_matches:
        cgpa = float(cgpa_matches[0])
        if cgpa >= 8.5 and cgpa <= 10:
            cgpa_bonus = 10
        elif cgpa >= 7.5:
            cgpa_bonus = 5
    
    # Calculate education score
    if resume_edu_level >= jd_edu_level:
        base_score = 20
    else:
        base_score = 10
    
    return min(20, base_score + cgpa_bonus)


def calculate_experience_adjustment(
    resume_years: float,
    required_years: float | None,
    is_entry_level: bool,
    has_internship: bool,
    has_projects: bool,
) -> dict:
    """Calculate experience-based adjustments."""
    adjustment = {
        "bonus_points": 0,
        "notes": "",
        "valid_experience": resume_years,
    }
    
    if is_entry_level:
        # For entry-level roles, projects and internships count as experience
        counted_years = resume_years
        if has_internship and resume_years < 1:
            counted_years += 0.5
            adjustment["notes"] = "Internship counted as 0.5 years for entry-level role"
        if has_projects and resume_years < 1:
            adjustment["bonus_points"] = 15
            adjustment["notes"] = "Strong projects compensate for limited experience"
        
        adjustment["valid_experience"] = counted_years
        return adjustment
    
    # For non-entry-level roles
    if required_years is None:
        return adjustment
    
    if resume_years >= required_years:
        adjustment["bonus_points"] = 10
        adjustment["notes"] = f"Meets experience requirement ({resume_years}+ years)"
    elif resume_years >= required_years * 0.8:
        adjustment["bonus_points"] = 5
        adjustment["notes"] = f"Slightly under requirement but close ({resume_years} vs {required_years}+ years)"
    
    return adjustment


def calculate_smart_score(
    matched_skills: list[str],
    missing_skills: list[str],
    is_entry_level: bool,
    resume_years: float,
    required_years: float | None,
    has_internship: bool,
    has_projects: bool,
    education_score: int,
) -> dict:
    """
    Intelligent score calculation using weighted skills and context.
    
    Returns dict with:
    - score: Final 0-100 score
    - skill_score: Score from skill matching
    - experience_bonus: Bonus from experience/internships/projects
    - education_score: Bonus from education
    - reasoning: Human-readable explanation
    """
    
    # Initialize
    total_weight = 0
    matched_weight = 0
    
    # Weight all skills
    all_skills = set(matched_skills + missing_skills)
    skill_breakdown = {}
    
    for skill in all_skills:
        weight = _get_skill_weight(skill)
        total_weight += weight
        skill_breakdown[skill] = weight
        
        if skill in matched_skills:
            matched_weight += weight
    
    # Calculate base skill score (0-70)
    if total_weight > 0:
        skill_coverage = matched_weight / total_weight
        skill_score = skill_coverage * 70
    else:
        skill_score = 50
    
    # Calculate experience adjustment
    exp_adjustment = calculate_experience_adjustment(
        resume_years, required_years, is_entry_level, has_internship, has_projects
    )
    experience_bonus = exp_adjustment["bonus_points"]
    
    # Calculate penalty for missing high-value skills
    missing_high_value = [s for s in missing_skills if _get_skill_weight(s) == 3]
    penalty = len(missing_high_value) * 3  # 3 points per missing high-value skill
    
    # Final score calculation
    final_score = skill_score + experience_bonus + education_score - penalty
    final_score = max(0, min(100, final_score))
    
    # Generate reasoning
    reasoning = f"Matched {len(matched_skills)}/{len(all_skills)} required skills"
    if is_entry_level and experience_bonus > 0:
        reasoning += f" (entry-level: {exp_adjustment['notes']})"
    if education_score > 0:
        reasoning += f" with strong education (+{education_score}pts)"
    
    return {
        "score": int(final_score),
        "skill_score": int(skill_score),
        "experience_bonus": experience_bonus,
        "education_score": education_score,
        "missing_high_value_skills": missing_high_value,
        "reasoning": reasoning,
        "is_entry_level": is_entry_level,
        "valid_experience": exp_adjustment["valid_experience"],
        "skill_breakdown": skill_breakdown,
    }


def calculate_required_years(jd_text: str) -> float | None:
    """Extract required years of experience from JD."""
    if not jd_text:
        return None
    
    # Look for patterns like "3 years", "3+ years", "3-5 years"
    matches = re.findall(r"(\d+)\s*\+?\s*(?:years?|yrs?)", jd_text.lower())
    if matches:
        return float(max(int(m) for m in matches))
    return None


def apply_semantic_skill_matching(
    matched_skills: list[str],
    missing_skills: list[str],
    jd_text: str,
    resume_text: str,
) -> tuple[list[str], list[str]]:
    """
    Apply semantic matching to catch similar terms.
    E.g., "RAG pipeline" should match "RAG Architecture"
    """
    # Semantic aliases
    aliases = {
        "llm": ["large language model", "llms", "groq"],
        "rag": ["retrieval-augmented generation", "rag pipeline", "rag architecture"],
        "dl": ["deep learning", "deep-learning"],
        "ml": ["machine learning", "machine-learning"],
        "cv": ["computer vision", "vision"],
        "nlp": ["natural language processing"],
        "auth": ["authentication", "oauth", "jwt"],
        "db": ["database", "sql"],
        "fe": ["frontend", "front-end"],
        "be": ["backend", "back-end"],
    }
    
    matched_lower = [s.lower() for s in matched_skills]
    missing_lower = [s.lower() for s in missing_skills]
    
    # Check for semantic matches in missing skills
    newly_matched = []
    still_missing = []
    
    for missing in missing_skills:
        missing_l = missing.lower()
        found_match = False
        
        # Check if any alias matches
        for alias_group in aliases.values():
            if any(variant in matched_lower for variant in alias_group):
                if any(variant in missing_l.split() for variant in alias_group):
                    found_match = True
                    break
        
        # Check for direct substring matches
        if not found_match:
            for matched in matched_skills:
                if matched.lower() in missing_l or missing_l in matched.lower():
                    found_match = True
                    break
        
        if found_match:
            newly_matched.append(missing)
        else:
            still_missing.append(missing)
    
    # Update lists
    final_matched = matched_skills + newly_matched
    final_missing = still_missing
    
    return final_matched, final_missing
