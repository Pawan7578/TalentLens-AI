from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# Auth
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str
    id: int


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# Job Templates
class JobTemplateCreate(BaseModel):
    job_role: str
    description: str
    reference_resume_text: str


class JobTemplateOut(BaseModel):
    id: int
    job_role: str
    description: str
    reference_resume_text: str
    created_at: datetime

    class Config:
        from_attributes = True


class JobTemplateBasic(BaseModel):
    id: int
    job_role: str
    created_at: datetime

    class Config:
        from_attributes = True


# Submissions
class SubmissionOut(BaseModel):
    """Submission view - shows admin fields only for admin users"""
    id: int
    user_id: int
    job_template_id: Optional[int] = None
    jd_text: str
    resume_filename: str
    ats_score: float
    skill_match: Optional[float] = None
    education_match: Optional[float] = None
    experience_match: Optional[float] = None
    missing_skills: Optional[str] = None
    education_gap: Optional[str] = None
    experience_gap: Optional[str] = None
    feedback: str
    status: str
    email_sent: Optional[bool] = False
    llm_provider: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SubmissionAdminOut(BaseModel):
    """Admin view: Full detailed analysis - same as SubmissionOut"""
    id: int
    user_id: int
    job_template_id: Optional[int] = None
    jd_text: str
    resume_filename: str
    ats_score: float
    skill_match: Optional[float] = None
    education_match: Optional[float] = None
    experience_match: Optional[float] = None
    missing_skills: Optional[str] = None
    education_gap: Optional[str] = None
    experience_gap: Optional[str] = None
    feedback: str
    status: str
    email_sent: Optional[bool] = False
    llm_provider: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminSubmissionOut(BaseModel):
    """Admin submissions list"""
    id: int
    user_id: int
    user_name: str
    user_email: str
    job_template_id: Optional[int] = None
    jd_text: str
    resume_filename: str
    ats_score: float
    skill_match: Optional[float] = None
    education_match: Optional[float] = None
    experience_match: Optional[float] = None
    missing_skills: Optional[str] = None
    education_gap: Optional[str] = None
    experience_gap: Optional[str] = None
    feedback: str
    status: str
    email_sent: Optional[bool] = False
    llm_provider: Optional[str] = None
    created_at: datetime


class ProviderInfo(BaseModel):
    id: str
    label: str
    available: bool
    models: Optional[List[str]] = None


class StatusUpdate(BaseModel):
    status: str  # "selected" or "rejected"


class AnalyzeResponse(BaseModel):
    submission_id: int
    ats_score: float
    skill_match: float
    education_match: float
    experience_match: float
    missing_skills: List[str]
    education_gap: str
    experience_gap: str
    feedback: str


class AnalyzeResponseUser(BaseModel):
    """User view: Limited data"""
    submission_id: int
    ats_score: float
    feedback: str