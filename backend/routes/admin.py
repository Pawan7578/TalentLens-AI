from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
import auth
import os
import logging
import asyncio
from services.email_service import send_selected_email, send_rejected_email, send_selected_email_bulk, send_rejected_email_bulk
from services.file_parser import extract_text
import aiofiles
from pydantic import BaseModel
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Absolute path — same fix as routes/analyze.py
UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Submissions ───────────────────────────────────────────────────────────────

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
    return [
        schemas.AdminSubmissionOut(
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
            llm_provider=s.llm_provider or "unknown",
            created_at=s.created_at,
        )
        for s in submissions
    ]


@router.put("/submissions/{submission_id}/status")
def update_status(
    submission_id: int,
    update: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    submission = db.query(models.Submission).filter(
        models.Submission.id == submission_id
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.email_sent:
        raise HTTPException(status_code=400, detail="Email already sent for this submission")
    if update.status not in ("selected", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'selected' or 'rejected'")

    submission.status = update.status

    user = db.query(models.User).filter(models.User.id == submission.user_id).first()
    try:
        if update.status == "selected":
            send_selected_email(user.email, user.name)
        else:
            send_rejected_email(user.email, user.name)
        submission.email_sent = True
    except Exception as e:
        logger.warning(f"Email send failed (status still updated): {e}")

    db.commit()
    return {
        "message": f"Submission marked as {update.status}",
        "email_sent": submission.email_sent,
    }


@router.get("/resume/{submission_id}")
def download_resume(
    submission_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    submission = db.query(models.Submission).filter(
        models.Submission.id == submission_id
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    file_path = os.path.join(UPLOAD_DIR, submission.resume_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Resume file not found on server")

    return FileResponse(file_path, filename=submission.resume_filename)


# ── Bulk Email ────────────────────────────────────────────────────────────────

class BulkEmailCandidate(BaseModel):
    id: int
    name: str
    email: str
    score: float

class BulkEmailRequest(BaseModel):
    candidates: List[BulkEmailCandidate]
    email_type: str  # "selected" or "rejected"

@router.post("/bulk-email")
async def bulk_email(
    request: BulkEmailRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    """
    Send bulk selection or rejection emails to multiple candidates.
    - candidates: List of candidates {id, name, email, score}
    - email_type: "selected" or "rejected"
    """
    if not request.candidates:
        raise HTTPException(status_code=400, detail="No candidates provided")
    
    if request.email_type not in ("selected", "rejected"):
        raise HTTPException(status_code=400, detail="email_type must be 'selected' or 'rejected'")
    
    emails = [c.email for c in request.candidates]
    names = [c.name for c in request.candidates]
    
    try:
        # Send bulk emails with automatic delays
        if request.email_type == "selected":
            result = send_selected_email_bulk(emails, names)
        else:
            result = send_rejected_email_bulk(emails, names)
        
        # Update submission records
        for candidate in request.candidates:
            submission = db.query(models.Submission).filter(
                models.Submission.id == candidate.id
            ).first()
            if submission:
                submission.status = request.email_type
                submission.email_sent = True
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Bulk email sent successfully",
            "sent": result['success_count'],
            "failed": result['failure_count'],
            "total": result['total'],
            "details": result,
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Bulk email error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send bulk emails: {str(e)}")


# ── Job Templates ─────────────────────────────────────────────────────────────

@router.post("/job-template", response_model=schemas.JobTemplateOut)
async def create_job_template(
    job_role: str = Form(...),
    description: str = Form(...),
    reference_resume: UploadFile = File(None),
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    """
    Create a new job template.
    - job_role:         Job title (e.g. "Senior Python Developer")
    - description:      Full job description text
    - reference_resume: Optional reference resume file (pdf / docx / txt)
    """
    logger.info(f"Creating job template: {job_role}")

    if not job_role or len(job_role.strip()) < 2:
        raise HTTPException(status_code=400, detail="Job role is required (min 2 chars)")
    if not description or len(description.strip()) < 10:
        raise HTTPException(status_code=400, detail="Description is required (min 10 chars)")

    # Extract reference resume text (optional)
    resume_text = "[No reference resume provided]"
    if reference_resume:
        try:
            resume_bytes = await reference_resume.read()
            if len(resume_bytes) == 0:
                raise ValueError("Reference resume file is empty")
            extracted = extract_text(reference_resume.filename, resume_bytes)
            resume_text = extracted if extracted and len(extracted.strip()) >= 10 else \
                "[Reference resume provided but text could not be extracted]"
            logger.info(f"Reference resume extracted: {len(resume_text)} chars")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Resume parsing error: {str(e)}")

    # Prevent duplicate job roles (case-insensitive)
    existing = db.query(models.JobTemplate).filter(
        models.JobTemplate.job_role.ilike(job_role.strip())
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Job template '{job_role}' already exists",
        )

    template = models.JobTemplate(
        job_role=job_role.strip(),
        description=description.strip(),
        reference_resume_text=resume_text.strip(),
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    logger.info(f"Job template created: ID={template.id}, Role={template.job_role}")
    return template


@router.get("/job-templates", response_model=list[schemas.JobTemplateBasic])
def list_job_templates(
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
    return (
        db.query(models.JobTemplate)
        .order_by(models.JobTemplate.created_at.desc())
        .all()
    )


@router.get("/job-templates/{template_id}", response_model=schemas.JobTemplateOut)
def get_job_template_detail(
    template_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(auth.require_admin),
):
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
    template = db.query(models.JobTemplate).filter(
        models.JobTemplate.id == template_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Job template not found")

    submission_count = db.query(models.Submission).filter(
        models.Submission.job_template_id == template_id
    ).count()
    if submission_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete template: {submission_count} submission(s) reference it",
        )

    db.delete(template)
    db.commit()
    logger.info(f"Job template deleted: ID={template_id}")
    return {"message": "Job template deleted successfully"}


# ── SMTP diagnostic endpoint ──────────────────────────────────────────────────

@router.get("/smtp-check")
def smtp_check(
    _: models.User = Depends(auth.require_admin),
):
    """
    Admin-only: verify SMTP config is working without sending a real email.
    Hit GET /admin/smtp-check after deployment to confirm email is ready.
    """
    from services.email_service import verify_smtp_config
    result = verify_smtp_config()
    status_code = 200 if result.get("auth_ok") else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=result, status_code=status_code)
