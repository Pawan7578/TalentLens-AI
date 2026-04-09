"""
email_service.py — SMTP email sender for TalentLens AI.

Works identically in local dev and on Render — both use Gmail SMTP with
App Passwords over STARTTLS (port 587).

Required environment variables (backend/.env locally, Render env vars in prod):
    SMTP_HOST     = smtp.gmail.com
    SMTP_PORT     = 587
    SMTP_USER     = your-email@example.com
    SMTP_PASSWORD = <16-char Gmail App Password — NOT your Gmail password>
    SMTP_FROM     = your-email@example.com

How to get a Gmail App Password:
    Google Account → Security → 2-Step Verification → App Passwords
    → Select app: Mail  → Select device: Other → name it "TalentLens"
    → Copy the 16-character password shown

FIXES FOR BULK EMAIL SENDING:
    - Added proper email headers (Message-ID, Date) to prevent spam filtering
    - Added delays between bulk emails to avoid Gmail rate limiting
    - Added email validation and retry logic
    - Support for bulk sending with automatic rate limiting
"""

import smtplib
import os
import logging
import time
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Connection timeout — prevents the request hanging indefinitely if Gmail is slow
SMTP_TIMEOUT = 15
# Gmail rate limits: ~20 emails per hour, 500 per day
RATE_LIMIT_DELAY = 3  # seconds between emails
BULK_EMAIL_RETRY_ATTEMPTS = 3


def _get_smtp_config() -> dict:
    """
    Read SMTP settings fresh from env on every call.

    Reading at call-time (not module import time) ensures the values
    are always correct even if dotenv loads after this module first imports.
    """
    user = os.getenv("SMTP_USER", "")
    return {
        "host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     user,
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from":     os.getenv("SMTP_FROM", user),  # fallback from to user
    }


def validate_email(email: str) -> bool:
    """
    Validate email format using regex.
    
    Returns:
        True if email format is valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def _send_email(to_email: str, subject: str, html_body: str, retry_count: int = 0) -> None:
    """
    Send an HTML email via Gmail SMTP (STARTTLS on port 587).
    
    Includes:
    - Email validation
    - Proper email headers (Message-ID, Date) to prevent spam filtering
    - Retry logic for transient failures
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        retry_count: Internal counter for retry attempts
    
    Raises:
        ValueError:   Invalid email or SMTP credentials not configured
        RuntimeError: Any SMTP / network failure (with a human-readable message)
    """
    
    # Validate email format
    if not validate_email(to_email):
        raise ValueError(f"Invalid email address format: {to_email}")
    
    cfg = _get_smtp_config()

    if not cfg["user"] or not cfg["password"]:
        raise ValueError(
            "SMTP credentials not configured. "
            "Set SMTP_USER and SMTP_PASSWORD in your environment."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg["from"]
    msg["To"]      = to_email
    
    # ✅ ADD PROPER EMAIL HEADERS TO PREVENT SPAM FILTERING
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="talentlens.ai")
    msg["X-Priority"] = "3"
    msg["X-Mailer"] = "TalentLens AI HR System"
    
    msg.attach(MIMEText(html_body, "html"))

    logger.info(f"📧 Sending email to {to_email} (attempt {retry_count + 1})")

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()   # re-identify after STARTTLS upgrade
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"], to_email, msg.as_string())
        logger.info(f"✅ Email sent successfully to {to_email}")

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP auth failed: {e}")
        raise RuntimeError(
            "Gmail authentication failed. "
            "SMTP_PASSWORD must be a 16-character Gmail App Password, "
            "not your regular Gmail password. "
            "Generate one at: Google Account → Security → App Passwords."
        ) from e

    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Recipient refused {to_email}: {e}")
        raise RuntimeError(f"Email address refused by server: {to_email}") from e

    except smtplib.SMTPException as e:
        # Retry on transient SMTP errors
        if retry_count < BULK_EMAIL_RETRY_ATTEMPTS:
            logger.warning(f"⚠️ SMTP error, retry {retry_count + 1}/{BULK_EMAIL_RETRY_ATTEMPTS}")
            time.sleep(5)  # Wait 5 seconds before retry
            return _send_email(to_email, subject, html_body, retry_count + 1)
        
        logger.error(f"SMTP error after {BULK_EMAIL_RETRY_ATTEMPTS} retries: {e}")
        raise RuntimeError(f"SMTP error (after retries): {e}") from e

    except TimeoutError as e:
        logger.error(f"SMTP timeout ({cfg['host']}:{cfg['port']})")
        raise RuntimeError(
            f"SMTP connection timed out after {SMTP_TIMEOUT}s — "
            "check SMTP_HOST / SMTP_PORT."
        ) from e

    except OSError as e:
        # Covers DNS failures, connection refused, network unreachable
        logger.error(f"Network error to SMTP: {e}")
        raise RuntimeError(
            f"Cannot reach SMTP server {cfg['host']}:{cfg['port']} — {e}"
        ) from e


def send_selected_email(to_email: str, name: str) -> None:
    """Send a shortlisting congratulations email."""
    subject = "Congratulations — Your Resume is Shortlisted"
    html = f"""
    <html>
    <body style="font-family: Georgia, serif; color: #1a1a1a; max-width: 600px; margin: auto; padding: 40px;">
      <h2 style="color: #15803d;">Congratulations, {name}!</h2>
      <p>We are pleased to inform you that your resume has been shortlisted for the position.</p>
      <p>Our team will review your application in detail and contact you shortly with the next steps.</p>
      <br/>
      <p style="color: #6b7280; font-size: 13px;">This is an automated notification from the TalentLens AI HR system.</p>
    </body>
    </html>
    """
    _send_email(to_email, subject, html)


def send_selected_email_bulk(to_emails: List[str], names: List[str]) -> dict:
    """
    Send shortlisting emails to multiple recipients with automatic rate limiting.
    
    This function sends emails with configurable delays between each to avoid
    Gmail's rate limiting (which blocks ~20+ emails/hour sent rapidly).
    
    Args:
        to_emails: List of recipient email addresses
        names: List of recipient names (must match length of to_emails)
    
    Returns:
        dict with keys:
            - 'sent': List of successfully sent email addresses
            - 'failed': List of failed addresses with error reasons
            - 'total': Total recipients processed
    
    Example:
        >>> result = send_selected_email_bulk(
        ...     ['user1@gmail.com', 'user2@gmail.com'],
        ...     ['User 1', 'User 2']
        ... )
        >>> print(f"Sent: {len(result['sent'])}, Failed: {len(result['failed'])}")
    """
    
    if len(to_emails) != len(names):
        raise ValueError("Email list and names list must have the same length")
    
    if not to_emails:
        logger.warning("Empty recipient list provided to send_selected_email_bulk")
        return {'sent': [], 'failed': [], 'total': 0}
    
    sent = []
    failed = []
    
    logger.info(f"📧 Starting bulk send to {len(to_emails)} recipients with {RATE_LIMIT_DELAY}s delays")
    
    for i, (email, name) in enumerate(zip(to_emails, names), 1):
        try:
            send_selected_email(email, name)
            sent.append(email)
            logger.info(f"✅ [{i}/{len(to_emails)}] {email}")
            
            # Add delay between emails to avoid Gmail rate limiting
            if i < len(to_emails):  # Don't delay after last email
                logger.debug(f"⏳ Waiting {RATE_LIMIT_DELAY}s before next email...")
                time.sleep(RATE_LIMIT_DELAY)
        
        except Exception as e:
            error_msg = str(e)
            failed.append({'email': email, 'name': name, 'error': error_msg})
            logger.error(f"❌ [{i}/{len(to_emails)}] {email}: {error_msg}")
    
    result = {
        'sent': sent,
        'failed': failed,
        'total': len(to_emails),
        'success_count': len(sent),
        'failure_count': len(failed),
    }
    
    logger.info(
        f"📊 Bulk send complete: {len(sent)}/{len(to_emails)} successful, "
        f"{len(failed)} failed"
    )
    
    return result


def send_rejected_email(to_email: str, name: str) -> None:
    """Send an application rejection email."""
    subject = "Application Update — TalentLens AI"
    html = f"""
    <html>
    <body style="font-family: Georgia, serif; color: #1a1a1a; max-width: 600px; margin: auto; padding: 40px;">
      <h2 style="color: #b91c1c;">Application Status Update</h2>
      <p>Dear {name},</p>
      <p>We regret to inform you that after careful review, your application has not been shortlisted at this time.</p>
      <p>We appreciate the time and effort you put into your application and wish you the very best in your search.</p>
      <br/>
      <p style="color: #6b7280; font-size: 13px;">This is an automated notification from the TalentLens AI HR system.</p>
    </body>
    </html>
    """
    _send_email(to_email, subject, html)


def send_rejected_email_bulk(to_emails: List[str], names: List[str]) -> dict:
    """
    Send rejection emails to multiple recipients with automatic rate limiting.
    
    Args:
        to_emails: List of recipient email addresses
        names: List of recipient names
    
    Returns:
        dict with 'sent', 'failed', 'total' keys (same format as send_selected_email_bulk)
    """
    
    if len(to_emails) != len(names):
        raise ValueError("Email list and names list must have the same length")
    
    sent = []
    failed = []
    
    logger.info(f"📧 Starting bulk rejection send to {len(to_emails)} recipients")
    
    for i, (email, name) in enumerate(zip(to_emails, names), 1):
        try:
            send_rejected_email(email, name)
            sent.append(email)
            
            if i < len(to_emails):
                time.sleep(RATE_LIMIT_DELAY)
        
        except Exception as e:
            failed.append({'email': email, 'name': name, 'error': str(e)})
            logger.error(f"Failed to send rejection to {email}: {e}")
    
    return {
        'sent': sent,
        'failed': failed,
        'total': len(to_emails),
        'success_count': len(sent),
        'failure_count': len(failed),
    }


def verify_smtp_config() -> dict:
    """
    Smoke-test SMTP connectivity without sending a real email.
    Use this in your /health or /admin/smtp-check endpoint.

    Returns a status dict — does NOT raise, always returns safely.
    """
    cfg = _get_smtp_config()
    result = {
        "host":       cfg["host"],
        "port":       cfg["port"],
        "user":       cfg["user"],
        "configured": bool(cfg["user"] and cfg["password"]),
        "reachable":  False,
        "auth_ok":    False,
        "error":      None,
    }

    if not result["configured"]:
        result["error"] = "SMTP_USER or SMTP_PASSWORD is not set"
        return result

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            result["reachable"] = True
            server.login(cfg["user"], cfg["password"])
            result["auth_ok"] = True
    except smtplib.SMTPAuthenticationError as e:
        result["reachable"] = True
        result["error"] = (
            "Auth failed — SMTP_PASSWORD must be a Gmail App Password (16 chars), "
            f"not your account password. Detail: {str(e)[:120]}"
        )
    except Exception as e:
        result["error"] = str(e)

    return result
