import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config

MAIL_SERVER = config.MAIL_SERVER
MAIL_PORT = config.MAIL_PORT
MAIL_USERNAME = config.MAIL_USERNAME
MAIL_PASSWORD = config.MAIL_PASSWORD

def send_otp_email(recipient_email, otp_code, purpose="Registration"):
    """
    Dispatches a 6-digit OTP code to the target recipient_email via Gmail SMTP.
    Falls back gracefully to Development Mode (console logging) if SMTP is unconfigured.
    """
    subject_title = "Account Verification Code" if purpose.lower() == "registration" else "Password Reset Request"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #090d16; color: #f8fafc; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: #131b2e; border-radius: 16px; border: 1px solid rgba(148, 163, 184, 0.1); padding: 32px; box-shadow: 0 20px 40px rgba(0,0,0,0.3); }}
            .badge {{ display: inline-block; background: rgba(37, 99, 235, 0.15); color: #3b82f6; padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
            h2 {{ color: #ffffff; margin-top: 16px; font-size: 1.5rem; }}
            p {{ color: #94a3b8; font-size: 0.95rem; line-height: 1.6; }}
            .otp-box {{ background: rgba(37, 99, 235, 0.1); border: 1px solid #2563eb; color: #60a5fa; font-size: 2.2rem; font-weight: 800; text-align: center; padding: 16px; border-radius: 12px; letter-spacing: 0.25em; margin: 24px 0; }}
            .footer {{ font-size: 0.8rem; color: #64748b; margin-top: 24px; border-top: 1px solid rgba(148, 163, 184, 0.1); padding-top: 16px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <span class="badge">Sales Manager Security</span>
            <h2>{subject_title}</h2>
            <p>Use the 6-digit verification code below to complete your {purpose.lower()}:</p>
            <div class="otp-box">{otp_code}</div>
            <p>This code is valid for <strong>10 minutes</strong>. If you did not request this code, please ignore this email.</p>
            <div class="footer">
                Sales Manager System &bull; Secure Authentication
            </div>
        </div>
    </body>
    </html>
    """

    # If no Gmail App Password or username is configured, run in Development Mode
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("\n" + "=" * 60)
        print(f"[DEV MODE EMAIL DISPATCH]")
        print(f"To: {recipient_email}")
        print(f"Purpose: {purpose}")
        print(f"VERIFICATION CODE: {otp_code}")
        print("=" * 60 + "\n")
        return {"success": True, "dev_mode": True, "otp_code": otp_code}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Sales Manager - {subject_title}"
        msg["From"] = f"Sales Manager Security <{MAIL_USERNAME}>"
        msg["To"] = recipient_email

        text_part = MIMEText(f"Your Sales Manager verification code for {purpose} is: {otp_code}. Valid for 10 minutes.", "plain")
        html_part = MIMEText(html_content, "html")

        msg.attach(text_part)
        msg.attach(html_part)

        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, recipient_email, msg.as_string())
        server.quit()

        return {"success": True, "dev_mode": False}
    except Exception as e:
        print(f"[EMAIL DISPATCH ERROR] Could not send live email: {e}")
        print(f"[FALLBACK LOG] Verification Code for {recipient_email}: {otp_code}")
        return {"success": True, "dev_mode": True, "otp_code": otp_code, "error": str(e)}
