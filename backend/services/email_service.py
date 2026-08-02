import smtplib
from email.message import EmailMessage

from flask import current_app


def email_is_configured():
    return bool(
        current_app.config.get("SMTP_USERNAME")
        and current_app.config.get("SMTP_APP_PASSWORD")
        and current_app.config.get("EMAIL_FROM")
    )


def send_otp_email(recipient, code, purpose):
    if not email_is_configured():
        raise RuntimeError(
            "Email delivery is not configured. Set SMTP_USERNAME, "
            "SMTP_APP_PASSWORD, and EMAIL_FROM."
        )

    if purpose == "verify_email":
        subject = "Verify your Pipeline.sh email"
        heading = "Complete your Pipeline.sh registration"
    else:
        subject = "Reset your Pipeline.sh password"
        heading = "Reset your Pipeline.sh password"

    expiry = current_app.config["OTP_EXPIRY_MINUTES"]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config["EMAIL_FROM"]
    message["To"] = recipient
    message.set_content(
        f"{heading}\n\n"
        f"Your one-time verification code is: {code}\n\n"
        f"This code expires in {expiry} minutes. "
        "If you did not request it, you can ignore this email."
    )

    with smtplib.SMTP_SSL(
        current_app.config["SMTP_HOST"],
        current_app.config["SMTP_PORT"],
        timeout=15,
    ) as smtp:
        smtp.login(
            current_app.config["SMTP_USERNAME"],
            current_app.config["SMTP_APP_PASSWORD"],
        )
        smtp.send_message(message)
