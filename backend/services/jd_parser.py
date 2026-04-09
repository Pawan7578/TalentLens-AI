"""
Job Description Parser - Analyzes JD to determine role level and expectations.

Detects entry-level vs senior roles and automatically adjusts scoring.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def detect_job_level(jd_text: str) -> dict:
    """
    Detect if JD is entry-level, mid-level, or senior level friendly.
    
    Returns:
        {
            "level": "entry" | "mid" | "senior",
            "expected_years": int,
            "is_entry_level_friendly": bool,
            "confidence": float (0-1)
        }
    """
    if not jd_text:
        return {
            "level": "mid",
            "expected_years": 0,
            "is_entry_level_friendly": False,
            "confidence": 0.0,
        }
    
    jd_lower = jd_text.lower()
    
    # Entry-level indicators
    entry_indicators = [
        "entry-level", "entry level", "entry_level",
        "fresher", "fresh graduate",
        "junior", "jr.",
        "0-1", "0 to 1", "0-2", "0 to 2",
        "recent graduate", "new graduate",
        "associate", "trainee", "intern",
        "early career", "0 years experience",
        "first-time", "first time",
    ]
    
    # Senior/experienced indicators
    senior_indicators = [
        "senior", "sr.",
        "lead", "tech lead",
        "principal",
        "staff",
        "architect", "architecture",
        "10+", "10 years", "15+", "15 years",
        "manager", "engineering manager",
        "director", "head of",
        "expert",
    ]
    
    # Count matches
    entry_count = sum(1 for ind in entry_indicators if ind in jd_lower)
    senior_count = sum(1 for ind in senior_indicators if ind in jd_lower)
    
    # Extract expected years of experience
    exp_match = re.search(r"(\d+)\+?\s*(?:years?|yrs?)", jd_lower)
    expected_years = int(exp_match.group(1)) if exp_match else 0
    
    # Determine level
    if entry_count >= 1 or (expected_years <= 2 and entry_count >= 0):
        level = "entry"
        is_entry_friendly = True
        confidence = min(1.0, entry_count * 0.3 + 0.5)
    elif senior_count >= 1 or expected_years >= 8:
        level = "senior"
        is_entry_friendly = False
        confidence = min(1.0, senior_count * 0.3 + 0.5)
    else:
        level = "mid"
        is_entry_friendly = expected_years <= 4
        confidence = 0.6
    
    logger.info(f"📋 Job Level Detection: {level.upper()} (entry_friendly={is_entry_friendly}, exp={expected_years}yrs)")
    
    return {
        "level": level,
        "expected_years": expected_years,
        "is_entry_level_friendly": is_entry_friendly,
        "confidence": confidence,
    }


def extract_required_experience(jd_text: str) -> Optional[int]:
    """Extract required years of experience from JD."""
    if not jd_text:
        return None
    
    # Look for patterns like "3 years", "5+ years", "10-15 years"
    match = re.search(r"(\d+)\s*\+?\s*(?:years?|yrs?)", jd_text.lower())
    return int(match.group(1)) if match else None


def get_role_title(jd_text: str) -> Optional[str]:
    """Extract job title from JD if present."""
    if not jd_text:
        return None
    
    lines = jd_text.split('\n')
    
    # Check first few lines for title patterns
    for line in lines[:5]:
        line = line.strip()
        if any(word in line.lower() for word in ["position", "title", "role"]):
            return line.replace("Position:", "").replace("Title:", "").replace("Role:", "").strip()
    
    return None


def adjust_score_by_level(
    raw_score: int,
    jd_level: dict,
    resume_has_internship: bool,
    resume_has_projects: bool,
) -> tuple[int, str]:
    """
    Adjust score based on job level and candidate background.
    
    Returns:
        (adjusted_score, adjustment_reasoning)
    """
    adjustment = 0
    reasoning_parts = []
    
    if jd_level["is_entry_level_friendly"]:
        # Entry-level role
        if resume_has_internship:
            adjustment += 15
            reasoning_parts.append(f"+15 for internship experience (entry-level friendly role)")
        
        if resume_has_projects:
            adjustment += 10
            reasoning_parts.append(f"+10 for projects (counts as experience for entry-level)")
        
        if raw_score >= 60:
            # Boost high-scoring entry-level candidates
            adjustment += min(10, (raw_score - 60) * 0.2)  # Additional boost for strong matches
            reasoning_parts.append(f"+{min(10, (raw_score - 60) * 0.2):.0f} for strong match")
    
    elif jd_level["level"] == "senior":
        # Senior role - penalize if candidate experience is low
        expected_years = jd_level["expected_years"]
        # This penalty would be calculated elsewhere based on resume experience
        reasoning_parts.append(f"Senior role consideration (expects {expected_years}+ years)")
    
    else:
        # Mid-level role
        if resume_has_projects:
            adjustment += 5
            reasoning_parts.append(f"+5 for projects (mid-level role)")
    
    adjusted = min(100, max(0, raw_score + adjustment))
    reasoning = "; ".join(reasoning_parts) if reasoning_parts else "No level adjustments"
    
    return adjusted, reasoning


def calculate_experience_threshold(jd_text: str) -> dict:
    """Calculate experience matching requirements from JD."""
    
    required_years = extract_required_experience(jd_text)
    level = detect_job_level(jd_text)
    
    # Calculate thresholds
    if level["is_entry_level_friendly"]:
        min_threshold = 0.0
        ideal_threshold = 1.0
        exceeds_threshold = 2.0
    elif level["level"] == "senior":
        min_threshold = required_years or 8
        ideal_threshold = (required_years or 8) + 2
        exceeds_threshold = (required_years or 8) + 5
    else:
        min_threshold = max(1, (required_years or 3) - 2)
        ideal_threshold = required_years or 3
        exceeds_threshold = (required_years or 3) + 2
    
    return {
        "min_threshold": min_threshold,
        "ideal_threshold": ideal_threshold,
        "exceeds_threshold": exceeds_threshold,
        "required_years": required_years,
    }


def analyze_skill_emphasis(jd_text: str) -> dict:
    """Analyze which skills are emphasized in the JD."""
    
    if not jd_text:
        return {"primary_skills": [], "secondary_skills": []}
    
    jd_lower = jd_text.lower()
    
    # Common skill/tech keywords
    tech_keywords = {
        # Languages
        "python": "Python",
        "java": "Java",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "golang": "Go",
        "rust": "Rust",
        
        # Frameworks/Libraries
        "react": "React",
        "vue": "Vue",
        "angular": "Angular",
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "nodejs": "Node.js",
        "node.js": "Node.js",
        
        # Databases
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "mongodb": "MongoDB",
        "redis": "Redis",
        
        # ML/AI
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "keras": "Keras",
        "llm": "LLM",
        "rag": "RAG",
        "groq": "Groq",
        
        # Cloud/DevOps
        "aws": "AWS",
        "azure": "Azure",
        "gcp": "GCP",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        
        # Other
        "git": "Git",
        "sql": "SQL",
    }
    
    # Count mentions of each skill
    skill_counts = {}
    for keyword, name in tech_keywords.items():
        count = len(re.findall(rf"\b{re.escape(keyword)}\b", jd_lower))
        if count > 0:
            skill_counts[name] = count
    
    # Sort by frequency
    sorted_skills = sorted(skill_counts.items(), key=lambda x: -x[1])
    
    # Split into primary (mentioned 3+) and secondary (mentioned 1-2)
    primary_skills = [skill for skill, count in sorted_skills if count >= 2]
    secondary_skills = [skill for skill, count in sorted_skills if count == 1]
    
    return {
        "primary_skills": primary_skills[:10],
        "secondary_skills": secondary_skills[:10],
        "skill_emphasis": skill_counts,
    }
