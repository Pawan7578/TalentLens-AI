from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
import auth
import os
import logging
import uuid
from services.email_service import send_selected_email, send_rejected_email
from services.file_parser import extract_text
import aiofiles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("/submissions", response_model=list[schemas.AdminSubmissionOut])
def list_all_submissions(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    submissions = (
        db.query(models.Submission)
        .join(models.User)
        .order_by(models.Submission.created_at.desc())
        .all()
    )
    result = []
    for s in submissions:
        result.append(schemas.AdminSubmissionOut(
            id=s.id,
            user_id=s.user_id,
            user_name=s.user.name,
            user_email=s.user.email,
            job_template_id=s.job_template_id,
            jd_text=s.jd_text,
            resume_filename=s.resume_filename,
            ats_score=s.ats_score,
            skill_match=s.skill_match,
            education_match=s.education_match,
            experience_match=s.experience_match,
            missing_skills=s.missing_skills,
            education_gap=s.education_gap,
            experience_gap=s.experience_gap,
            feedback=s.feedback,
            status=s.status,
            email_sent=s.email_sent,
            llm_provider=s.llm_provider or "ollama",
            created_at=s.created_at,
        ))
    return result


@router.put("/submissions/{submission_id}/status")
def update_status(
    submission_id: int,
    update: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.email_sent:
        raise HTTPException(status_code=400, detail="Email already sent for this submission")
    if update.status not in ("selected", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'selected' or 'rejected'")

    submission.status = update.status

    # Send email
    user = db.query(models.User).filter(models.User.id == submission.user_id).first()
    try:
        if update.status == "selected":
            send_selected_email(user.email, user.name)
        else:
            send_rejected_email(user.email, user.name)
        submission.email_sent = True
    except Exception as e:
        # Don't block status update if email fails — log and continue
        print(f"Email send failed: {e}")

    db.commit()
    return {"message": f"Submission marked as {update.status}", "email_sent": submission.email_sent}


@router.get("/resume/{submission_id}")
def download_resume(
    submission_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    file_path = os.path.join(UPLOAD_DIR, submission.resume_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume file not found")
    return FileResponse(file_path, filename=submission.resume_filename)


# ── JOB TEMPLATE MANAGEMENT ──────────────────────────────────────────────────


@router.post("/job-template", response_model=schemas.JobTemplateOut)
async def create_job_template(
    job_role: str = Form(...),
    description: str = Form(...),
    reference_resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    """
    Create a new job template by uploading:
    - job_role: The job title (e.g., "Senior Python Developer")
    - description: Full job description
    - reference_resume: Reference resume file (pdf/docx/txt) - OPTIONAL
    """
    logger.info(f"Creating job template: {job_role}")
    print(f"DEBUG - ROLE: {job_role}")
    print(f"DEBUG - DESC: {description[:50]}...")
    print(f"DEBUG - FILE: {reference_resume}")

    # Validate inputs
    if not job_role or len(job_role.strip()) < 2:
        raise HTTPException(status_code=400, detail="Job role is required (min 2 chars)")

    if not description or len(description.strip()) < 10:
        raise HTTPException(status_code=400, detail="Description is required (min 10 chars)")

    # Extract reference resume text (optional)
    resume_text = ""
    if reference_resume:
        try:
            resume_bytes = await reference_resume.read()
            if len(resume_bytes) == 0:
                raise ValueError("Reference resume file is empty")

            logger.info(f"Extracting text from reference resume: {reference_resume.filename}")
            resume_text = extract_text(reference_resume.filename, resume_bytes)

            if not resume_text or len(resume_text.strip()) < 10:
                logger.warning("Extracted resume text < 10 chars, using default")
                resume_text = "[Reference resume provided but could not extract text]"

            logger.info(f"Reference resume extracted: {len(resume_text)} chars")
        except ValueError as e:
            logger.error(f"Resume extraction failed: {e}")
            raise HTTPException(status_code=400, detail=f"Resume parsing error: {str(e)}")
    else:
        logger.info("No reference resume provided (optional)")
        resume_text = "[No reference resume provided]"

    # Check for duplicate job role
    existing = db.query(models.JobTemplate).filter(
        models.JobTemplate.job_role.ilike(job_role)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Job template '{job_role}' already exists"
        )

    # Create template
    template = models.JobTemplate(
        job_role=job_role.strip(),
        description=description.strip(),
        reference_resume_text=resume_text.strip(),
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    logger.info(f"Job template created: ID={template.id}, Role={job_role}")
    return template


@router.get("/job-templates", response_model=list[schemas.JobTemplateBasic])
def list_job_templates(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    """List all job templates (admin only)."""
    templates = db.query(models.JobTemplate).order_by(
        models.JobTemplate.created_at.desc()
    ).all()
    return templates


@router.get("/job-templates/{template_id}", response_model=schemas.JobTemplateOut)
def get_job_template_detail(
    template_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    """Get detailed job template (admin only)."""
    template = db.query(models.JobTemplate).filter(
        models.JobTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Job template not found")
    return template


@router.delete("/job-templates/{template_id}")
def delete_job_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    """Delete a job template (admin only)."""
    template = db.query(models.JobTemplate).filter(
        models.JobTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Job template not found")

    # Check for submissions using this template
    submission_count = db.query(models.Submission).filter(
        models.Submission.job_template_id == template_id
    ).count()

    if submission_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete template with {submission_count} submissions"
        )

    db.delete(template)
    db.commit()

    logger.info(f"Job template deleted: ID={template_id}")
    return {"message": "Job template deleted successfully"}