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


class LoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class LoginUser(BaseModel):
    id: str
    email: EmailStr
    name: str


class Token(BaseModel):
    token: str
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    role: str
    name: str
    id: int
    user: LoginUser


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None
    refreshToken: Optional[str] = None


class RefreshTokenResponse(BaseModel):
    token: str
    access_token: str
    refresh_token: str
    token_type: str


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
    final_score: float
    keyword_score: float
    ai_score: float
    matched_skills: List[str]
    missing_skills: List[str]
    cleaned_skills: Optional[List[str]] = None
    suggestions: List[str]
    ai_unavailable: bool = False

    # Compatibility fields for existing frontend/admin views.
    submission_id: Optional[int] = None
    ats_score: Optional[float] = None
    skill_match: Optional[float] = None
    education_match: Optional[float] = None
    experience_match: Optional[float] = None
    education_gap: Optional[str] = None
    experience_gap: Optional[str] = None
    feedback: Optional[str] = None


class AnalyzeResponseUser(BaseModel):
    """User view: Limited data"""
    submission_id: int
    ats_score: float
    feedback: str