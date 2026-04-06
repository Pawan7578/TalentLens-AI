import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")


def _send_email(to_email: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to_email, msg.as_string())


def send_selected_email(to_email: str, name: str):
    subject = "Congratulations — Your Resume is Shortlisted"
    html = f"""
    <html><body style="font-family: Georgia, serif; color: #1a1a1a; max-width: 600px; margin: auto; padding: 40px;">
      <h2 style="color: #15803d;">Congratulations, {name}!</h2>
      <p>We are pleased to inform you that your resume has been shortlisted for the position.</p>
      <p>Our team will review your application in detail and contact you shortly with the next steps.</p>
      <br/>
      <p style="color: #6b7280; font-size: 13px;">This is an automated notification from the HR team.</p>
    </body></html>
    """
    _send_email(to_email, subject, html)


def send_rejected_email(to_email: str, name: str):
    subject = "Application Update"
    html = f"""
    <html><body style="font-family: Georgia, serif; color: #1a1a1a; max-width: 600px; margin: auto; padding: 40px;">
      <h2 style="color: #b91c1c;">Application Status Update</h2>
      <p>Dear {name},</p>
      <p>We regret to inform you that after careful review, your application has not been shortlisted at this time.</p>
      <p>We appreciate the time and effort you put into your application and wish you the very best in your search.</p>
      <br/>
      <p style="color: #6b7280; font-size: 13px;">This is an automated notification from the HR team.</p>
    </body></html>
    """
    _send_email(to_email, subject, html)