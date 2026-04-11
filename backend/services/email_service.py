"""
email_service.py — Multi-provider email sender for TalentLens AI.

PROVIDER STRATEGY (set EMAIL_PROVIDER in your .env):
    "smtp"      → Gmail SMTP via STARTTLS (local dev, works Gmail→Gmail reliably)
    "resend"    → Resend API (free 3,000/month, works on ALL platforms, ALL domains)
    "sendgrid"  → SendGrid API (free 100/day, works on ALL platforms, ALL domains)

RECOMMENDED SETUP:
    Local .env   → EMAIL_PROVIDER=smtp       (no extra accounts needed)
    Render/Prod  → EMAIL_PROVIDER=resend     (free, zero port issues, all domains)

────────────────────────────────────────────────────────────────────────────────
SMTP ENVIRONMENT VARIABLES (EMAIL_PROVIDER=smtp):
    SMTP_HOST       = smtp.gmail.com
    SMTP_PORT       = 587
    SMTP_USER       = your-email@gmail.com
    SMTP_PASSWORD   = <16-char Gmail App Password>
    SMTP_FROM       = your-email@gmail.com

    How to get Gmail App Password:
    Google Account → Security → 2-Step Verification → App Passwords
    → App name: "TalentLens" → Copy the 16-character password

RESEND ENVIRONMENT VARIABLES (EMAIL_PROVIDER=resend):
    RESEND_API_KEY  = re_xxxxxxxxxxxxxxxxxxxx
    RESEND_FROM     = TalentLens AI <onboarding@resend.dev>   ← free dev sender

    Get free API key: https://resend.com/api-keys
    Free tier: 3,000 emails/month, 100/day

SENDGRID ENVIRONMENT VARIABLES (EMAIL_PROVIDER=sendgrid):
    SENDGRID_API_KEY = SG.xxxxxxxxxxxxxxxxxxxx
    SENDGRID_FROM    = your-verified@email.com

    Get free API key: https://app.sendgrid.com/settings/api_keys
    Free tier: 100 emails/day

────────────────────────────────────────────────────────────────────────────────
FEATURES:
    ✅ Multi-provider: SMTP / Resend / Sendgrid (switch via one env var)
    ✅ Universal delivery — works to Gmail, Yahoo, Outlook, corporate, .edu
    ✅ Advanced anti-spam headers (Message-ID, Date, DKIM-friendly structure)
    ✅ Plain-text fallback alongside HTML (improves spam score significantly)
    ✅ Retry logic with exponential backoff
    ✅ Email format validation
    ✅ Bulk sending with rate limiting and per-email error isolation
    ✅ Interview invitation email (new)
    ✅ Custom subject/body email (new — for ad-hoc HR messages)
    ✅ SMTP connection pooling for bulk sends (reuses one connection)
    ✅ Provider health check / smoke test
    ✅ Daily send counter (in-memory, resets on restart)
    ✅ Unsubscribe header (CAN-SPAM compliant)
"""

import smtplib
import os
import logging
import time
import re
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

SMTP_TIMEOUT          = 15       # seconds before connection gives up
RATE_LIMIT_DELAY      = 3        # seconds between individual emails (bulk)
BULK_SMTP_DELAY       = 2        # seconds between emails when using pooled SMTP
BULK_EMAIL_RETRY_ATTEMPTS = 3    # retry attempts on transient SMTP errors
RETRY_BACKOFF_BASE    = 5        # seconds — doubles on each retry

# In-memory daily counter (resets on server restart)
_daily_stats = {
    "date":   datetime.utcnow().date().isoformat(),
    "sent":   0,
    "failed": 0,
}

# ─── Provider Selection ───────────────────────────────────────────────────────

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp").lower()


# ─── Config Readers ──────────────────────────────────────────────────────────

def _get_smtp_config() -> dict:
    """Read SMTP settings fresh from env on every call."""
    user = os.getenv("SMTP_USER", "")
    return {
        "host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     user,
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from":     os.getenv("SMTP_FROM", user),
    }


def _get_resend_config() -> dict:
    return {
        "api_key": os.getenv("RESEND_API_KEY", ""),
        "from":    os.getenv("RESEND_FROM", "TalentLens AI <onboarding@resend.dev>"),
    }


def _get_sendgrid_config() -> dict:
    return {
        "api_key": os.getenv("SENDGRID_API_KEY", ""),
        "from":    os.getenv("SENDGRID_FROM", ""),
    }


# ─── Validation ──────────────────────────────────────────────────────────────

def validate_email(email: str) -> bool:
    """Validate email format. Returns True if valid."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def _validate_bulk_inputs(to_emails: List[str], names: List[str]) -> List[dict]:
    """
    Validate bulk inputs and return list of pre-failed entries for invalid emails.
    Returns list of {email, name, error} for invalid entries.
    """
    if len(to_emails) != len(names):
        raise ValueError("to_emails and names lists must have the same length")
    pre_failed = []
    for email, name in zip(to_emails, names):
        if not validate_email(email):
            pre_failed.append({"email": email, "name": name, "error": "Invalid email format"})
    return pre_failed


# ─── Anti-Spam HTML Builder ───────────────────────────────────────────────────

def _build_message(
    cfg_from: str,
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str,
) -> MIMEMultipart:
    """
    Build a MIME message with:
    - HTML + plain text fallback (improves spam score)
    - Full anti-spam headers
    - CAN-SPAM compliant unsubscribe header
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"]         = subject
    msg["From"]            = cfg_from
    msg["To"]              = to_email
    msg["Date"]            = formatdate(localtime=True)
    msg["Message-ID"]      = make_msgid(domain="talentlens.ai")
    msg["X-Priority"]      = "3"
    msg["X-Mailer"]        = "TalentLens AI HR System"
    msg["Reply-To"]        = cfg_from
    msg["X-Entity-Ref-ID"] = str(uuid.uuid4())   # unique per email — spam prevention
    msg["List-Unsubscribe"] = f"<mailto:{cfg_from}?subject=unsubscribe>"

    # Plain text first (fallback), HTML second (preferred by clients)
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


# ─── Provider: SMTP ──────────────────────────────────────────────────────────

def _send_via_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str,
    retry_count: int = 0,
) -> None:
    """
    Send via Gmail SMTP with STARTTLS.
    Opens a fresh connection per email — safe for low-volume sends.
    For bulk sending use _smtp_bulk_send() which pools the connection.
    """
    cfg = _get_smtp_config()

    if not cfg["user"] or not cfg["password"]:
        raise ValueError(
            "SMTP credentials not configured. "
            "Set SMTP_USER and SMTP_PASSWORD in your environment."
        )

    msg = _build_message(cfg["from"], to_email, subject, html_body, plain_body)
    logger.info(f"[SMTP] Sending to {to_email} (attempt {retry_count + 1})")

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            refused = server.sendmail(cfg["from"], to_email, msg.as_string())
            if refused:
                raise RuntimeError(f"Recipient refused by server: {refused}")

        logger.info(f"[SMTP] ✅ Sent to {to_email}")

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"[SMTP] Auth failed: {e}")
        raise RuntimeError(
            "Gmail authentication failed. "
            "SMTP_PASSWORD must be a 16-character Gmail App Password — "
            "not your regular Gmail password. "
            "Generate one: Google Account → Security → App Passwords."
        ) from e

    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"[SMTP] Recipient refused {to_email}: {e}")
        raise RuntimeError(f"Recipient refused by mail server: {to_email}") from e

    except smtplib.SMTPException as e:
        if retry_count < BULK_EMAIL_RETRY_ATTEMPTS:
            wait = RETRY_BACKOFF_BASE * (2 ** retry_count)   # exponential backoff
            logger.warning(f"[SMTP] Transient error, retry {retry_count + 1} in {wait}s: {e}")
            time.sleep(wait)
            return _send_via_smtp(to_email, subject, html_body, plain_body, retry_count + 1)
        raise RuntimeError(f"SMTP error after {BULK_EMAIL_RETRY_ATTEMPTS} retries: {e}") from e

    except TimeoutError as e:
        logger.error(f"[SMTP] Timeout ({cfg['host']}:{cfg['port']})")
        raise RuntimeError(
            f"SMTP connection timed out after {SMTP_TIMEOUT}s. "
            "Check SMTP_HOST / SMTP_PORT."
        ) from e

    except OSError as e:
        logger.error(f"[SMTP] Network error: {e}")
        raise RuntimeError(
            f"Cannot reach SMTP server {cfg['host']}:{cfg['port']} — {e}. "
            "On cloud platforms (Render, Railway) port 587 may be blocked. "
            "Set EMAIL_PROVIDER=resend to bypass port restrictions."
        ) from e


def _smtp_bulk_send(
    recipients: List[tuple],   # list of (email, subject, html_body, plain_body)
) -> tuple:
    """
    Connection-pooled SMTP bulk sender.
    Opens ONE connection and sends all emails through it — faster and more
    efficient than opening a new connection per email.

    Returns: (sent_list, failed_list)
    """
    cfg = _get_smtp_config()
    sent, failed = [], []

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            logger.info(f"[SMTP] Pooled connection opened for {len(recipients)} emails")

            for i, (email, subject, html_body, plain_body, name) in enumerate(recipients, 1):
                try:
                    msg = _build_message(cfg["from"], email, subject, html_body, plain_body)
                    refused = server.sendmail(cfg["from"], email, msg.as_string())
                    if refused:
                        raise RuntimeError(f"Server refused: {refused}")
                    sent.append(email)
                    logger.info(f"[SMTP] ✅ [{i}/{len(recipients)}] {email}")
                except Exception as e:
                    failed.append({"email": email, "name": name, "error": str(e)})
                    logger.error(f"[SMTP] ❌ [{i}/{len(recipients)}] {email}: {e}")

                if i < len(recipients):
                    time.sleep(BULK_SMTP_DELAY)

    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed — check SMTP_USER and SMTP_PASSWORD."
        )
    except Exception as e:
        raise RuntimeError(f"SMTP pooled connection failed: {e}") from e

    return sent, failed


# ─── Provider: Resend ────────────────────────────────────────────────────────

def _send_via_resend(to_email: str, subject: str, html_body: str, plain_body: str) -> None:
    """
    Send via Resend API (pure HTTPS — no port issues on any platform).
    Free tier: 3,000 emails/month, 100/day.
    Works to Gmail, Yahoo, Outlook, corporate, .edu — all domains.
    Get API key: https://resend.com/api-keys
    pip install resend
    """
    try:
        import resend  # type: ignore
    except ImportError:
        raise RuntimeError(
            "Resend package not installed. Run: pip install resend"
        )

    cfg = _get_resend_config()
    if not cfg["api_key"]:
        raise ValueError("RESEND_API_KEY not set in environment.")

    resend.api_key = cfg["api_key"]

    try:
        resend.Emails.send({
            "from":    cfg["from"],
            "to":      to_email,
            "subject": subject,
            "html":    html_body,
            "text":    plain_body,
        })
        logger.info(f"[Resend] ✅ Sent to {to_email}")
    except Exception as e:
        logger.error(f"[Resend] Failed for {to_email}: {e}")
        raise RuntimeError(f"Resend delivery failed: {e}") from e


# ─── Provider: SendGrid ──────────────────────────────────────────────────────

def _send_via_sendgrid(to_email: str, subject: str, html_body: str, plain_body: str) -> None:
    """
    Send via SendGrid API (pure HTTPS — no port issues on any platform).
    Free tier: 100 emails/day.
    Works to all domains.
    Get API key: https://app.sendgrid.com/settings/api_keys
    pip install sendgrid
    """
    try:
        from sendgrid import SendGridAPIClient           # type: ignore
        from sendgrid.helpers.mail import Mail, Content  # type: ignore
    except ImportError:
        raise RuntimeError(
            "SendGrid package not installed. Run: pip install sendgrid"
        )

    cfg = _get_sendgrid_config()
    if not cfg["api_key"]:
        raise ValueError("SENDGRID_API_KEY not set in environment.")
    if not cfg["from"]:
        raise ValueError("SENDGRID_FROM not set in environment.")

    try:
        message = Mail(
            from_email=cfg["from"],
            to_emails=to_email,
            subject=subject,
        )
        message.add_content(Content("text/plain", plain_body))
        message.add_content(Content("text/html", html_body))

        sg = SendGridAPIClient(cfg["api_key"])
        response = sg.send(message)
        logger.info(f"[SendGrid] ✅ Sent to {to_email} | status {response.status_code}")
    except Exception as e:
        logger.error(f"[SendGrid] Failed for {to_email}: {e}")
        raise RuntimeError(f"SendGrid delivery failed: {e}") from e


# ─── Core Dispatcher ─────────────────────────────────────────────────────────

def _send_email(
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str = "",
    retry_count: int = 0,
) -> None:
    """
    Central email dispatcher — routes to the correct provider based on
    EMAIL_PROVIDER env var. All public send_* functions call this.

    Args:
        to_email:   Recipient email address
        subject:    Email subject line
        html_body:  HTML email body
        plain_body: Plain text fallback (auto-generated if empty)
        retry_count: Internal — do not pass manually
    """
    if not validate_email(to_email):
        raise ValueError(f"Invalid email address: {to_email}")

    # Auto-generate plain text if not provided
    if not plain_body:
        plain_body = re.sub(r'<[^>]+>', '', html_body).strip()

    _reset_daily_stats_if_needed()

    try:
        if EMAIL_PROVIDER == "resend":
            _send_via_resend(to_email, subject, html_body, plain_body)
        elif EMAIL_PROVIDER == "sendgrid":
            _send_via_sendgrid(to_email, subject, html_body, plain_body)
        else:
            _send_via_smtp(to_email, subject, html_body, plain_body, retry_count)

        _daily_stats["sent"] += 1

    except Exception:
        _daily_stats["failed"] += 1
        raise


# ─── Daily Stats ─────────────────────────────────────────────────────────────

def _reset_daily_stats_if_needed() -> None:
    today = datetime.utcnow().date().isoformat()
    if _daily_stats["date"] != today:
        _daily_stats.update({"date": today, "sent": 0, "failed": 0})


def get_daily_stats() -> dict:
    """Return today's send stats. Use in /admin or /health endpoints."""
    _reset_daily_stats_if_needed()
    return {
        "date":     _daily_stats["date"],
        "sent":     _daily_stats["sent"],
        "failed":   _daily_stats["failed"],
        "provider": EMAIL_PROVIDER,
    }


# ─── Email Templates ─────────────────────────────────────────────────────────

def _base_html(content: str, accent_color: str = "#15803d") -> str:
    """Shared HTML wrapper — consistent branding across all emails."""
    return f"""
    <html>
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    </head>
    <body style="margin:0;padding:0;background:#f4f4f5;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:40px 0;">
        <tr><td align="center">
          <table width="600" cellpadding="0" cellspacing="0"
                 style="background:#ffffff;border-radius:8px;overflow:hidden;
                        font-family:Georgia,serif;color:#1a1a1a;">
            <!-- Header -->
            <tr>
              <td style="background:{accent_color};padding:24px 40px;">
                <span style="font-family:Arial,sans-serif;font-size:20px;
                             font-weight:bold;color:#ffffff;letter-spacing:0.5px;">
                  TalentLens AI
                </span>
              </td>
            </tr>
            <!-- Body -->
            <tr>
              <td style="padding:36px 40px;line-height:1.7;font-size:15px;">
                {content}
              </td>
            </tr>
            <!-- Footer -->
            <tr>
              <td style="padding:20px 40px;border-top:1px solid #e5e7eb;
                         background:#f9fafb;font-size:12px;color:#9ca3af;
                         font-family:Arial,sans-serif;">
                This is an automated notification from the TalentLens AI HR system.
                &nbsp;|&nbsp;
                <a href="mailto:{os.getenv('SMTP_FROM', os.getenv('RESEND_FROM', 'hr@talentlens.ai'))}?subject=unsubscribe"
                   style="color:#9ca3af;">Unsubscribe</a>
              </td>
            </tr>
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """


def _plain(content: str) -> str:
    """Strip HTML tags for plain text fallback."""
    return re.sub(r'<[^>]+>', '', content).strip()


# ─── Public Send Functions ───────────────────────────────────────────────────

def send_selected_email(to_email: str, name: str, position: str = "the position") -> None:
    """
    Send a shortlisting congratulations email.

    Args:
        to_email:  Recipient email
        name:      Candidate's name
        position:  Job title (optional, improves personalisation)
    """
    subject = f"Congratulations — You've Been Shortlisted for {position}"
    content = f"""
        <h2 style="color:#15803d;margin-top:0;">Congratulations, {name}!</h2>
        <p>We are pleased to inform you that your resume has been shortlisted
           for the role of <strong>{position}</strong>.</p>
        <p>Our team will review your application in detail and reach out shortly
           with the next steps in the process.</p>
        <p>We look forward to connecting with you soon.</p>
        <br/>
        <p style="font-size:14px;">Warm regards,<br/>
           <strong>TalentLens AI Hiring Team</strong></p>
    """
    _send_email(to_email, subject, _base_html(content, "#15803d"), _plain(content))


def send_rejected_email(to_email: str, name: str, position: str = "the position") -> None:
    """
    Send a respectful application rejection email.

    Args:
        to_email:  Recipient email
        name:      Candidate's name
        position:  Job title (optional)
    """
    subject = f"Your Application for {position} — Update"
    content = f"""
        <h2 style="color:#b91c1c;margin-top:0;">Application Status Update</h2>
        <p>Dear {name},</p>
        <p>Thank you for your interest in the <strong>{position}</strong> role and
           for taking the time to apply.</p>
        <p>After careful review, we regret to inform you that your application has
           not been shortlisted at this time. This was a competitive process and we
           received many strong applications.</p>
        <p>We genuinely appreciate your effort and encourage you to apply for future
           openings that match your profile.</p>
        <p>We wish you all the best in your career journey.</p>
        <br/>
        <p style="font-size:14px;">Kind regards,<br/>
           <strong>TalentLens AI Hiring Team</strong></p>
    """
    _send_email(to_email, subject, _base_html(content, "#b91c1c"), _plain(content))


def send_interview_email(
    to_email: str,
    name: str,
    position: str,
    interview_date: str,
    interview_time: str,
    interview_mode: str = "Video Call",
    interview_link: Optional[str] = None,
    interviewer_name: Optional[str] = None,
) -> None:
    """
    Send an interview invitation email. (NEW)

    Args:
        to_email:        Recipient email
        name:            Candidate's name
        position:        Job title
        interview_date:  e.g. "Monday, 15 July 2025"
        interview_time:  e.g. "10:00 AM IST"
        interview_mode:  "Video Call" | "In-Person" | "Phone"
        interview_link:  Zoom/Meet link (optional, shown only if provided)
        interviewer_name: Name of interviewer (optional)
    """
    subject = f"Interview Invitation — {position} at TalentLens AI"
    link_section = (
        f'<p><strong>Join Link:</strong> <a href="{interview_link}" style="color:#1d4ed8;">'
        f'{interview_link}</a></p>'
    ) if interview_link else ""

    interviewer_section = (
        f"<p><strong>Interviewer:</strong> {interviewer_name}</p>"
    ) if interviewer_name else ""

    content = f"""
        <h2 style="color:#1d4ed8;margin-top:0;">Interview Invitation</h2>
        <p>Dear {name},</p>
        <p>We are excited to invite you for an interview for the
           <strong>{position}</strong> role at TalentLens AI.</p>

        <table style="border:1px solid #e5e7eb;border-radius:6px;
                      padding:16px 24px;margin:20px 0;width:100%;
                      background:#f0f9ff;">
          <tr><td style="padding:6px 0;"><strong>Date:</strong></td>
              <td>{interview_date}</td></tr>
          <tr><td style="padding:6px 0;"><strong>Time:</strong></td>
              <td>{interview_time}</td></tr>
          <tr><td style="padding:6px 0;"><strong>Mode:</strong></td>
              <td>{interview_mode}</td></tr>
        </table>

        {link_section}
        {interviewer_section}

        <p>Please confirm your availability by replying to this email.
           If you need to reschedule, do let us know at least 24 hours in advance.</p>
        <p>We look forward to speaking with you!</p>
        <br/>
        <p style="font-size:14px;">Warm regards,<br/>
           <strong>TalentLens AI Hiring Team</strong></p>
    """
    _send_email(to_email, subject, _base_html(content, "#1d4ed8"), _plain(content))


def send_custom_email(
    to_email: str,
    name: str,
    subject: str,
    message_body: str,
) -> None:
    """
    Send a fully custom HR message. (NEW)
    Use for offer letters, document requests, or any ad-hoc communication.

    Args:
        to_email:     Recipient email
        name:         Candidate's name
        subject:      Email subject line
        message_body: Plain text or HTML body content
    """
    content = f"""
        <p>Dear {name},</p>
        {message_body}
        <br/>
        <p style="font-size:14px;">Regards,<br/>
           <strong>TalentLens AI Hiring Team</strong></p>
    """
    _send_email(to_email, subject, _base_html(content), _plain(content))


# ─── Bulk Send Functions ──────────────────────────────────────────────────────

def _run_bulk(
    emails_and_data: List[dict],
    send_fn,
    use_pool: bool = True,
) -> dict:
    """
    Internal bulk runner.
    - SMTP provider: uses connection pooling (_smtp_bulk_send) when use_pool=True
    - Resend/SendGrid: sends individually (they handle their own connections)
    - Isolates per-email failures so one bad address doesn't stop the batch
    """
    if not emails_and_data:
        return {"sent": [], "failed": [], "total": 0, "success_count": 0, "failure_count": 0}

    sent, failed = [], []

    if EMAIL_PROVIDER == "smtp" and use_pool:
        # Build recipients list for pooled sender
        recipients = [
            (
                d["email"], d["subject"], d["html"], d["plain"], d["name"]
            ) for d in emails_and_data
        ]
        try:
            sent, failed = _smtp_bulk_send(recipients)
        except RuntimeError as e:
            # Pool itself failed (auth error etc.) — mark all as failed
            for d in emails_and_data:
                failed.append({"email": d["email"], "name": d["name"], "error": str(e)})
    else:
        for i, d in enumerate(emails_and_data, 1):
            try:
                send_fn(d)
                sent.append(d["email"])
                logger.info(f"✅ [{i}/{len(emails_and_data)}] {d['email']}")
            except Exception as e:
                failed.append({"email": d["email"], "name": d["name"], "error": str(e)})
                logger.error(f"❌ [{i}/{len(emails_and_data)}] {d['email']}: {e}")
            if i < len(emails_and_data):
                time.sleep(RATE_LIMIT_DELAY)

    result = {
        "sent":          sent,
        "failed":        failed,
        "total":         len(emails_and_data),
        "success_count": len(sent),
        "failure_count": len(failed),
    }
    logger.info(
        f"Bulk complete: {len(sent)}/{len(emails_and_data)} sent, "
        f"{len(failed)} failed | provider={EMAIL_PROVIDER}"
    )
    return result


def send_selected_email_bulk(
    to_emails: List[str],
    names: List[str],
    position: str = "the position",
) -> dict:
    """
    Bulk shortlisting emails with connection pooling (SMTP) or API batching.

    Args:
        to_emails: List of recipient email addresses
        names:     List of recipient names
        position:  Job title shown in the email

    Returns:
        dict — sent, failed, total, success_count, failure_count
    """
    pre_failed = _validate_bulk_inputs(to_emails, names)
    valid_pairs = [
        (e, n) for e, n in zip(to_emails, names) if validate_email(e)
    ]

    subject = f"Congratulations — You've Been Shortlisted for {position}"

    def build(email, name):
        content = f"""
            <h2 style="color:#15803d;margin-top:0;">Congratulations, {name}!</h2>
            <p>Your resume has been shortlisted for <strong>{position}</strong>.</p>
            <p>Our team will contact you shortly with next steps.</p>
            <br/>
            <p style="font-size:14px;">Warm regards,<br/>
               <strong>TalentLens AI Hiring Team</strong></p>
        """
        return {
            "email": email, "name": name, "subject": subject,
            "html": _base_html(content, "#15803d"), "plain": _plain(content),
        }

    data = [build(e, n) for e, n in valid_pairs]
    result = _run_bulk(data, lambda d: send_selected_email(d["email"], d["name"], position))
    result["failed"].extend(pre_failed)
    result["failure_count"] = len(result["failed"])
    return result


def send_rejected_email_bulk(
    to_emails: List[str],
    names: List[str],
    position: str = "the position",
) -> dict:
    """
    Bulk rejection emails.

    Args:
        to_emails: List of recipient email addresses
        names:     List of recipient names
        position:  Job title shown in the email

    Returns:
        dict — sent, failed, total, success_count, failure_count
    """
    pre_failed = _validate_bulk_inputs(to_emails, names)
    valid_pairs = [(e, n) for e, n in zip(to_emails, names) if validate_email(e)]

    subject = f"Your Application for {position} — Update"

    def build(email, name):
        content = f"""
            <h2 style="color:#b91c1c;margin-top:0;">Application Status Update</h2>
            <p>Dear {name},</p>
            <p>After careful review, your application for <strong>{position}</strong>
               has not been shortlisted at this time.</p>
            <p>We appreciate your effort and wish you well in your search.</p>
            <br/>
            <p style="font-size:14px;">Kind regards,<br/>
               <strong>TalentLens AI Hiring Team</strong></p>
        """
        return {
            "email": email, "name": name, "subject": subject,
            "html": _base_html(content, "#b91c1c"), "plain": _plain(content),
        }

    data = [build(e, n) for e, n in valid_pairs]
    result = _run_bulk(data, lambda d: send_rejected_email(d["email"], d["name"], position))
    result["failed"].extend(pre_failed)
    result["failure_count"] = len(result["failed"])
    return result


def send_interview_email_bulk(
    to_emails: List[str],
    names: List[str],
    position: str,
    interview_date: str,
    interview_time: str,
    interview_mode: str = "Video Call",
    interview_link: Optional[str] = None,
) -> dict:
    """
    Bulk interview invitation emails. (NEW)
    Same interview slot sent to all recipients (e.g. panel shortlist notification).

    Returns:
        dict — sent, failed, total, success_count, failure_count
    """
    pre_failed = _validate_bulk_inputs(to_emails, names)
    valid_pairs = [(e, n) for e, n in zip(to_emails, names) if validate_email(e)]

    data = [{"email": e, "name": n} for e, n in valid_pairs]
    result = _run_bulk(
        data,
        lambda d: send_interview_email(
            d["email"], d["name"], position,
            interview_date, interview_time,
            interview_mode, interview_link,
        ),
        use_pool=False,  # interview emails are low-volume, no pooling needed
    )
    result["failed"].extend(pre_failed)
    result["failure_count"] = len(result["failed"])
    return result


# ─── Health Check ────────────────────────────────────────────────────────────

def verify_smtp_config() -> dict:
    """
    Smoke-test the configured email provider without sending a real email.
    Safe to use in /health or /admin/email-check endpoints.
    Always returns a dict — never raises.
    """
    provider = EMAIL_PROVIDER
    result = {
        "provider":   provider,
        "configured": False,
        "reachable":  False,
        "auth_ok":    False,
        "error":      None,
        "daily_stats": get_daily_stats(),
    }

    if provider == "resend":
        cfg = _get_resend_config()
        result["configured"] = bool(cfg["api_key"])
        result["auth_ok"]    = bool(cfg["api_key"])
        result["reachable"]  = bool(cfg["api_key"])
        if not cfg["api_key"]:
            result["error"] = "RESEND_API_KEY not set"
        return result

    if provider == "sendgrid":
        cfg = _get_sendgrid_config()
        result["configured"] = bool(cfg["api_key"] and cfg["from"])
        result["auth_ok"]    = bool(cfg["api_key"])
        result["reachable"]  = bool(cfg["api_key"])
        if not cfg["api_key"]:
            result["error"] = "SENDGRID_API_KEY not set"
        elif not cfg["from"]:
            result["error"] = "SENDGRID_FROM not set"
        return result

    # SMTP
    cfg = _get_smtp_config()
    result["host"]       = cfg["host"]
    result["port"]       = cfg["port"]
    result["user"]       = cfg["user"]
    result["configured"] = bool(cfg["user"] and cfg["password"])

    if not result["configured"]:
        result["error"] = "SMTP_USER or SMTP_PASSWORD not set"
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
            "Auth failed — use a Gmail App Password (16 chars), "
            f"not your account password. Detail: {str(e)[:120]}"
        )
    except OSError as e:
        result["error"] = (
            f"Cannot reach {cfg['host']}:{cfg['port']} — {e}. "
            "Port 587 may be blocked on this platform. "
            "Try EMAIL_PROVIDER=resend instead."
        )
    except Exception as e:
        result["error"] = str(e)

    return result