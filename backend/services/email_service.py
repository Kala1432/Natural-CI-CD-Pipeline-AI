import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------
BRAND_NAME = "FluxForge"
BRAND_TAGLINE = "Forge your pipelines with AI"
SUPPORT_EMAIL = "support@fluxforge.ai"

# Inline SVG mark for the email header — hexagon shield with infinity loop
LOGO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 64 64" role="img" aria-label="FluxForge">
  <path d="M32 3 L57 17 L57 47 L32 61 L7 47 L7 17 Z" fill="none" stroke="#ffffff" stroke-width="3.2" stroke-linejoin="round"/>
  <path d="M57 17 L57 47 L40 56.5" fill="none" stroke="#7dd3fc" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M22 32 a8 8 0 0 1 13 -4 a8 8 0 0 1 13 4 a8 8 0 0 1 -13 4 a8 8 0 0 1 -13 -4 z" fill="none" stroke="#7dd3fc" stroke-width="3.2" stroke-linecap="round"/>
  <line x1="35" y1="13" x2="35" y2="20" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>
  <circle cx="35" cy="13" r="2.2" fill="none" stroke="#ffffff" stroke-width="2"/>
  <line x1="29" y1="51" x2="29" y2="44" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>
  <circle cx="29" cy="51" r="2.2" fill="none" stroke="#ffffff" stroke-width="2"/>
</svg>
""".strip()


def _logo_for_email(uid: str) -> str:
    """Return the inline-SVG logo markup (gradient is white-on-navy for email header)."""
    return LOGO_SVG


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def email_is_configured() -> bool:
    return bool(
        current_app.config.get("SMTP_USERNAME")
        and current_app.config.get("SMTP_APP_PASSWORD")
        and current_app.config.get("EMAIL_FROM")
    )


def send_otp_email(recipient, code, purpose):
    """Send a one-time verification code to the given address.

    Uses a multipart/alternative payload so the user gets a beautiful HTML
    template in modern clients and a plain-text fallback in older clients
    or strict spam filters.
    """
    if not email_is_configured():
        raise RuntimeError(
            "Email delivery is not configured. Set SMTP_USERNAME, "
            "SMTP_APP_PASSWORD, and EMAIL_FROM."
        )

    if purpose == "verify_email":
        subject = f"Verify your {BRAND_NAME} email"
        heading = f"Complete your {BRAND_NAME} registration"
        cta_label = "Verify email"
    else:
        subject = f"Reset your {BRAND_NAME} password"
        heading = f"Reset your {BRAND_NAME} password"
        cta_label = "Reset password"

    expiry = current_app.config["OTP_EXPIRY_MINUTES"]

    # --- Build the email message -----------------------------------------
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = current_app.config["EMAIL_FROM"]
    message["To"] = recipient

    # 1) Plain text part — preserved for spam-filter safety & text clients
    plain_text = (
        f"{heading}\n\n"
        f"Your one-time verification code is: {code}\n\n"
        f"This code expires in {expiry} minutes. "
        f"If you did not request it, you can ignore this email."
    )
    message.attach(MIMEText(plain_text, "plain", "utf-8"))

    # 2) HTML part — branded template with inline logo
    uid = recipient.replace("@", "_at_").replace(".", "_")
    html_body = _render_html(heading, code, expiry, cta_label, purpose, uid)
    message.attach(MIMEText(html_body, "html", "utf-8"))

    # --- Send -------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Internal — HTML template
# ---------------------------------------------------------------------------
def _render_html(heading: str, code: str, expiry: int, cta_label: str,
                 purpose: str, uid: str) -> str:
    """Render the branded HTML email body."""
    logo = _logo_for_email(uid)
    code_html_safe = "".join(
        f'<span style="display:inline-block;width:34px;height:48px;line-height:48px;'
        f'margin:0 2px;font-size:28px;font-weight:700;color:#0f172a;'
        f'background:#f1f5f9;border:1px solid #cbd5e1;border-radius:8px;'
        f'text-align:center;font-family:\'SFMono-Regular\',Consolas,monospace;">{c}</span>'
        for c in code
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{heading}</title>
</head>
<body style="margin:0;padding:0;background:#0a0f1e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#e2e8f0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#0a0f1e;padding:40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="520" cellspacing="0" cellpadding="0" border="0" style="max-width:520px;background:#111827;border:1px solid rgba(255,255,255,0.08);border-radius:16px;overflow:hidden;">
          <!-- Header / brand banner -->
          <tr>
            <td style="background:linear-gradient(135deg,#6366f1 0%,#a855f7 100%);padding:28px 32px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td width="56" valign="middle" style="padding-right:14px;">{logo}</td>
                  <td valign="middle">
                    <div style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.01em;line-height:1.1;">{BRAND_NAME}</div>
                    <div style="color:rgba(255,255,255,0.85);font-size:12px;letter-spacing:0.06em;text-transform:uppercase;margin-top:2px;">{BRAND_TAGLINE}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h1 style="margin:0 0 8px;color:#f8fafc;font-size:22px;font-weight:600;line-height:1.3;">{heading}</h1>
              <p style="margin:0 0 24px;color:#94a3b8;font-size:14px;line-height:1.6;">
                Use the verification code below to {'confirm your email address' if purpose == 'verify_email' else 'complete your password reset'}. The code is single-use and expires in {expiry} minutes.
              </p>
              <!-- OTP box -->
              <div style="background:#0a0f1e;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px;text-align:center;margin-bottom:20px;">
                {code_html_safe}
              </div>
              <p style="margin:0 0 24px;color:#94a3b8;font-size:13px;line-height:1.6;">
                If the button below doesn't work, copy and paste this code into the {BRAND_NAME} app where prompted.
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 auto 24px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#6366f1,#a855f7);border-radius:8px;">
                    <a href="#" style="display:inline-block;padding:12px 28px;color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;letter-spacing:0.02em;">{cta_label}</a>
                  </td>
                </tr>
              </table>
              <p style="margin:0;color:#64748b;font-size:12px;line-height:1.6;">
                If you didn't request this email you can safely ignore it. Someone else may have typed your address by mistake.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;border-top:1px solid rgba(255,255,255,0.08);">
              <p style="margin:0 0 4px;color:#64748b;font-size:12px;">Sent by {BRAND_NAME} · <a href="mailto:{SUPPORT_EMAIL}" style="color:#94a3b8;text-decoration:underline;">{SUPPORT_EMAIL}</a></p>
              <p style="margin:0;color:#475569;font-size:11px;">© {BRAND_NAME} · AI-powered CI/CD pipeline automation</p>
            </td>
          </tr>
        </table>
        <p style="margin:20px 0 0;color:#475569;font-size:11px;text-align:center;">This is an automated message. Please do not reply directly to this email.</p>
      </td>
    </tr>
  </table>
</body>
</html>"""
