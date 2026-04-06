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
from services.analyzer import analyze_resume_vs_jd

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analyze"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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

    Parameters:
    - resume: Resume file (pdf/docx/txt)
    - jd_text: Job description text (alternative to jd_file)
    - jd_file: Job description file (alternative to jd_text)
    - job_template_id: Job template ID (optional, takes precedence over jd_text/jd_file)

    At least one of: jd_text, jd_file, OR job_template_id must be provided.
    """
    logger.info(f"Analyze request: user={current_user.id}, template_id={job_template_id}")

    # Determine job description
    job_template = None
    if job_template_id:
        # User selected a job template
        logger.info(f"Using job template: {job_template_id}")
        job_template = db.query(models.JobTemplate).filter(
            models.JobTemplate.id == job_template_id
        ).first()
        if not job_template:
            raise HTTPException(status_code=404, detail="Job template not found")
        job_description = job_template.description
    else:
        # Determine job description from text or file
        if jd_text and jd_text.strip():
            job_description = jd_text.strip()
            logger.info(f"Using provided jd_text: {len(job_description)} chars")
        elif jd_file:
            jd_bytes = await jd_file.read()
            if len(jd_bytes) == 0:
                raise HTTPException(status_code=400, detail="Job description file is empty")
            try:
                from services.file_parser import extract_text
                job_description = extract_text(jd_file.filename, jd_bytes)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide job description as text, file, or template ID"
            )

    if not job_description or len(job_description.strip()) < 10:
        raise HTTPException(status_code=400, detail="Job description is too short (min 10 chars)")

    # Extract resume text
    resume_bytes = await resume.read()

    logger.info(f"Processing resume: {resume.filename} ({len(resume_bytes)} bytes)")
    if len(resume_bytes) == 0:
        raise HTTPException(status_code=400, detail="Resume file is empty")

    try:
        # Call the analyzer service (handles extraction + LLM analysis)
        result = await analyze_resume_vs_jd(
            resume_bytes=resume_bytes,
            resume_filename=resume.filename,
            jd_text=job_description,
            provider=None,  # Use default
        )
    except ValueError as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during analysis: {e}")
        raise HTTPException(status_code=502, detail=f"Analysis service error: {str(e)}")

    # Save resume file
    ext = os.path.splitext(resume.filename)[1]
    saved_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, saved_filename)
    try:
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(resume_bytes)
        logger.info(f"Resume saved: {saved_filename}")
    except Exception as e:
        logger.error(f"Failed to save resume file: {e}")
        # Continue despite file save failure

    # Save to DB
    submission = models.Submission(
        user_id=current_user.id,
        job_template_id=job_template.id if job_template else None,
        jd_text=job_description,
        resume_filename=saved_filename,
        ats_score=float(result.get("overall_score", 50)),
        skill_match=float(result.get("skill_match", 50)),
        education_match=float(result.get("education_match", 50)),
        experience_match=float(result.get("experience_match", 50)),
        missing_skills=json.dumps(result.get("missing_skills", [])),
        education_gap=result.get("education_gap", ""),
        experience_gap=result.get("experience_gap", ""),
        feedback=result.get("feedback", ""),
        status="pending",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    logger.info(f"Submission saved: ID={submission.id}, Score={submission.ats_score}")

    # Always return full response - frontend will filter based on user role
    return schemas.AnalyzeResponse(
        submission_id=submission.id,
        ats_score=submission.ats_score,
        skill_match=submission.skill_match,
        education_match=submission.education_match,
        experience_match=submission.experience_match,
        missing_skills=result.get("missing_skills", []),
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
    
    # Return full data - frontend will filter based on user role
    return submissions


@router.get("/job-templates", response_model=list[schemas.JobTemplateOut])
def get_job_templates(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_user),
):
    """
    Get all available job templates for users to select from.
    Endpoint is public to authenticated users (not restricted to admin).
    """
    logger.info(f"User {current_user.id} listing job templates")
    templates = db.query(models.JobTemplate).order_by(
        models.JobTemplate.created_at.desc()
    ).all()
    return templates