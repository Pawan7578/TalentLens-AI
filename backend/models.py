from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    created_at = Column(DateTime, default=datetime.utcnow)

    submissions = relationship("Submission", back_populates="user")


class JobTemplate(Base):
    __tablename__ = "job_templates"

    id = Column(Integer, primary_key=True, index=True)
    job_role = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    reference_resume_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    submissions = relationship("Submission", back_populates="job_template")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_template_id = Column(Integer, ForeignKey("job_templates.id"), nullable=True)
    jd_text = Column(Text, nullable=False)
    resume_filename = Column(String, nullable=False)
    ats_score = Column(Float, default=0)
    skill_match = Column(Float, default=0)
    education_match = Column(Float, default=0)
    experience_match = Column(Float, default=0)
    missing_skills = Column(Text, default="[]")  # JSON string
    education_gap = Column(Text, default="")
    experience_gap = Column(Text, default="")
    feedback = Column(Text, default="")
    status = Column(String, default="pending")  # pending / selected / rejected
    email_sent = Column(Boolean, default=False)
    llm_provider = Column(String, default="groq")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="submissions")
    job_template = relationship("JobTemplate", back_populates="submissions")