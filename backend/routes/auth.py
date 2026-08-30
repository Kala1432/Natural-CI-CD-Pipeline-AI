import logging
import os
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, url_for, make_response
from flask_jwt_extended import (
    create_access_token, get_jwt_identity, jwt_required,
    set_access_cookies, unset_jwt_cookies
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.hash import argon2

from backend.repositories import (
    UserRepository,
    EmailOTPRepository,
    GithubConnectionRepository,
    AuditLogRepository,
)
from backend.repositories import to_str
from backend.services.email_service import email_is_configured, send_otp_email
from backend.services.audit_service import log_audit_event

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)
GITHUB_OAUTH_STATE_SALT = "github-oauth-state"
GITHUB_OAUTH_STATE_MAX_AGE = 10 * 60
OTP_PURPOSES = ("verify_email", "reset_password")


def _user_payload(user_dict: dict) -> dict:
    """Convert a user dict from repository to API payload."""
    profile = user_dict.get("profile", {})
    return {
        "id": user_dict["id"],
        "email": user_dict["email"],
        "name": user_dict.get("name", ""),
        "avatar_url": user_dict.get("avatar_url", ""),
        "role": user_dict.get("role", "developer"),
        "github_connected": profile.get("github_connected", False),
        "github_login": profile.get("github_login"),
        "notification_email": profile.get("notification_email") or user_dict["email"],
    }


def _get_user_repository():
    return UserRepository()


def _get_user(user_id_str):
    """Get user dict by ID string using repository."""
    if not user_id_str:
        return None
    try:
        user_repo = _get_user_repository()
        return user_repo.get_by_id_str(user_id_str)
    except Exception:
        return None


def _github_oauth_config():
    client_id = (current_app.config.get("GITHUB_CLIENT_ID") or os.environ.get("GITHUB_CLIENT_ID", "")).strip()
    client_secret = (current_app.config.get("GITHUB_CLIENT_SECRET") or os.environ.get("GITHUB_CLIENT_SECRET", "")).strip()
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def _github_state_serializer():
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt=GITHUB_OAUTH_STATE_SALT,
    )


def _github_frontend_redirect(**params):
    frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:3000")
    query = urlencode(params)
    return redirect(f"{frontend_url.rstrip('/')}/auth/github/success?{query}")


def _otp_hash(user_id, purpose, code):
    payload = f"{user_id}:{purpose}:{code}".encode()
    secret = current_app.config["SECRET_KEY"].encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _send_user_otp(user_id, purpose, enforce_cooldown=False):
    """Send OTP using repository pattern. Returns (code, retry_after_seconds)."""
    if purpose not in OTP_PURPOSES:
        raise ValueError("Invalid OTP purpose")

    now = datetime.utcnow()
    otp_repo = EmailOTPRepository()
    latest = otp_repo.latest_for(user_id, purpose)

    cooldown = current_app.config["OTP_RESEND_COOLDOWN_SECONDS"]
    if (
        enforce_cooldown
        and latest
        and latest.created_at
        and (now - latest.created_at).total_seconds() < cooldown
    ):
        remaining = cooldown - int((now - latest.created_at).total_seconds())
        return None, max(1, remaining)

    if not current_app.config.get("MAIL_SUPPRESS_SEND") and not email_is_configured():
        raise RuntimeError(
            "Email delivery is not configured. The administrator must configure Gmail SMTP."
        )

    # Consume any previous unused OTPs for this purpose
    for otp in otp_repo.find_by_user(user_id):
        if otp.purpose == purpose and not otp.consumed_at:
            otp.consumed_at = now
            otp.save()

    # Cryptographically secure random 6-digit numeric code (100,000 - 999,999)
    code = f"{secrets.randbelow(900_000) + 100_000}"
    user_repo = _get_user_repository()
    user_dict = user_repo.get_by_id_str(user_id)

    otp_repo.create_otp(
        user_id=user_id,
        purpose=purpose,
        code_hash=_otp_hash(user_id, purpose, code),
        expires_at=now + timedelta(
            minutes=current_app.config["OTP_EXPIRY_MINUTES"]
        ),
    )

    if not current_app.config.get("MAIL_SUPPRESS_SEND") and user_dict:
        try:
            send_otp_email(user_dict["email"], code, purpose)
        except Exception:
            raise
    return code, None


def _consume_user_otp(user_id, purpose, code):
    """Verify OTP using repository pattern. Returns (success, error_message)."""
    otp_repo = EmailOTPRepository()

    # Find the latest unused OTP for this purpose
    valid_otp = None
    for otp in otp_repo.find_by_user(user_id):
        if otp.purpose == purpose and not otp.consumed_at:
            valid_otp = otp
            break

    if not valid_otp:
        return False, "The code is invalid or has expired."

    now = datetime.utcnow()
    if valid_otp.expires_at and valid_otp.expires_at < now:
        return False, "The code is invalid or has expired."
    if valid_otp.attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        return False, "Too many incorrect attempts. Request a new code."

    if not hmac.compare_digest(
        valid_otp.code_hash or "",
        _otp_hash(user_id, purpose, str(code).strip()),
    ):
        otp_repo.increment_attempts(valid_otp)
        return False, "The code is invalid or has expired."

    otp_repo.consume(valid_otp)
    return True, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    user_repo = _get_user_repository()
    if user_repo.find_by_email(email):
        return jsonify({"error": "An account with this email already exists"}), 409

    verification_required = current_app.config["EMAIL_VERIFICATION_REQUIRED"]
    if (
        verification_required
        and not current_app.config.get("MAIL_SUPPRESS_SEND")
        and not email_is_configured()
    ):
        verification_required = False

    user = user_repo.create_user(
        email=email,
        password_hash=argon2.hash(password),
        name=name or email.split("@")[0],
        role="developer",
        email_verified=not verification_required,
        is_admin=False,
    )
    user_id = user.id

    log_audit_event(action="user.register", user_id=user_id, details={"email": user.email})

    if verification_required:
        try:
            _send_user_otp(user_id, "verify_email")
        except Exception:
            logger.exception("Registration OTP delivery failed")
            try:
                user_repo.delete_by_id(user_id)
            except Exception:
                pass
            return jsonify({"error": "Could not send the verification email. Please try again."}), 502
        response = {
            "message": "Verification code sent.",
            "email": user.email,
            "requires_verification": True,
        }
        return jsonify(response), 202

    token = create_access_token(identity=str(user_id))
    resp = jsonify({"user": _user_payload(user.to_dict())})
    set_access_cookies(resp, token)
    return resp, 201


@auth_bp.route("/verify-email", methods=["POST"])
def verify_email():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    code = str(data.get("otp", "")).strip()

    user_repo = _get_user_repository()
    user = user_repo.find_by_email(email)
    if not user or not code:
        return jsonify({"error": "A valid email and verification code are required"}), 400
    if user.email_verified:
        return jsonify({"error": "This email is already verified"}), 409

    user_id = user.id
    valid, error = _consume_user_otp(user_id, "verify_email", code)
    if not valid:
        log_audit_event("user.verify_email.failed", user_id=user_id, details={"error": error}, status="failure")
        return jsonify({"error": error}), 400

    # Update email_verified
    from backend.models_mongo import User
    User.objects(id=user_id).update(set__email_verified=True)
    log_audit_event("user.verify_email.success", user_id=user_id)

    user_dict = user_repo.get_by_id_str(user_id)
    token = create_access_token(identity=str(user_id))
    resp = jsonify({"user": _user_payload(user_dict)})
    set_access_cookies(resp, token)
    return resp


@auth_bp.route("/resend-verification", methods=["POST"])
def resend_verification():
    email = (request.get_json() or {}).get("email", "").strip().lower()
    user_repo = _get_user_repository()
    user = user_repo.find_by_email(email)
    if not user or user.email_verified:
        return jsonify({"message": "If verification is pending, a code will be sent."})

    user_id = user.id
    try:
        _, retry_after = _send_user_otp(user_id, "verify_email", enforce_cooldown=True)
    except Exception:
        logger.exception("Verification OTP resend failed")
        return jsonify({"error": "Could not send the verification email. Please try again."}), 502
    if retry_after:
        return jsonify({
            "error": f"Please wait {retry_after} seconds before requesting another code.",
            "retry_after": retry_after,
        }), 429
    return jsonify({"message": "Verification code sent."})


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = (request.get_json() or {}).get("email", "").strip().lower()
    user_repo = _get_user_repository()
    user = user_repo.find_by_email(email)
    response = {
        "message": "If an account exists for that email, a password reset code has been sent."
    }
    if not user or not user.email_verified:
        return jsonify(response)

    user_id = user.id
    try:
        _, retry_after = _send_user_otp(user_id, "reset_password", enforce_cooldown=True)
    except Exception:
        logger.exception("Password reset OTP delivery failed")
        return jsonify({"error": "Could not send the password reset email. Please try again."}), 502
    if retry_after:
        return jsonify({
            "error": f"Please wait {retry_after} seconds before requesting another code.",
            "retry_after": retry_after,
        }), 429
    return jsonify(response)


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    code = str(data.get("otp", "")).strip()
    new_password = data.get("new_password", "")
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    user_repo = _get_user_repository()
    user = user_repo.find_by_email(email)
    if not user or not code:
        return jsonify({"error": "The code is invalid or has expired."}), 400

    user_id = user.id
    valid, error = _consume_user_otp(user_id, "reset_password", code)
    if not valid:
        log_audit_event("user.reset_password.failed", user_id=user_id, details={"error": error}, status="failure")
        return jsonify({"error": error}), 400

    # Update password hash
    from backend.models_mongo import User
    User.objects(id=user_id).update(set__password_hash=argon2.hash(new_password))
    log_audit_event("user.reset_password.success", user_id=user_id)
    return jsonify({"message": "Password reset successfully. You can now sign in."})


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user_repo = _get_user_repository()
    user = user_repo.find_by_email(email)
    if not user or not user.password_hash:
        log_audit_event("user.login.failed", details={"email": email}, status="failure")
        return jsonify({"error": "Invalid email or password"}), 401

    try:
        valid = argon2.verify(password, user.password_hash)
    except Exception:
        valid = False

    if not valid:
        log_audit_event("user.login.failed", user_id=user.id, details={"email": email}, status="failure")
        return jsonify({"error": "Invalid email or password"}), 401

    if current_app.config["EMAIL_VERIFICATION_REQUIRED"] and not user.email_verified:
        return jsonify({
            "error": "Verify your email before signing in.",
            "requires_verification": True,
        }), 403

    user_id = user.id
    token = create_access_token(identity=str(user_id))
    log_audit_event("user.login.success", user_id=user_id)

    user_dict = user_repo.get_by_id_str(user_id)
    resp = jsonify({"user": _user_payload(user_dict)})
    set_access_cookies(resp, token)
    return resp


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = _get_user(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": _user_payload(user)})


@auth_bp.route("/google", methods=["POST"])
def google_signin():
    data = request.get_json() or {}
    id_token_str = data.get("id_token")
    if not id_token_str:
        return jsonify({"error": "id_token is required"}), 400

    resp = requests.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"id_token": id_token_str},
        timeout=10,
    )
    if not resp.ok:
        log_audit_event("user.google_signin.failed", details={"reason": "invalid_google_token"}, status="failure")
        return jsonify({"error": "Invalid Google token"}), 401

    import time
    info = resp.json()
    google_id = info.get("sub")
    email = info.get("email", "").lower()
    name = info.get("name", "")
    avatar_url = info.get("picture", "")

    # 1. Validate issuer (iss)
    iss = info.get("iss", "")
    if iss not in ("https://accounts.google.com", "accounts.google.com"):
        log_audit_event("user.google_signin.failed", details={"reason": "invalid_issuer", "iss": iss}, status="failure")
        return jsonify({"error": "Invalid Google token issuer"}), 401

    # 2. Validate expiration (exp)
    try:
        exp = int(info.get("exp", 0))
        if exp <= int(time.time()):
            log_audit_event("user.google_signin.failed", details={"reason": "token_expired"}, status="failure")
            return jsonify({"error": "Google token has expired"}), 401
    except (ValueError, TypeError):
        log_audit_event("user.google_signin.failed", details={"reason": "invalid_exp"}, status="failure")
        return jsonify({"error": "Invalid token expiration claim"}), 401

    # 3. Validate email_verified
    email_verified = info.get("email_verified")
    if email_verified not in (True, "true", "True", "1", 1):
        log_audit_event("user.google_signin.failed", details={"reason": "email_not_verified", "email": email}, status="failure")
        return jsonify({"error": "Google account email is not verified"}), 401

    # 4. Validate audience if client ID is configured
    configured_client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    if configured_client_id and info.get("aud") != configured_client_id:
        log_audit_event("user.google_signin.failed", details={"reason": "aud_mismatch"}, status="failure")
        return jsonify({"error": "Invalid Google token audience"}), 401

    if not google_id or not email:
        log_audit_event("user.google_signin.failed", details={"reason": "missing_required_fields"}, status="failure")
        return jsonify({"error": "Google token missing required fields"}), 400

    user_repo = _get_user_repository()
    user = user_repo.find_by_google_id(google_id)
    if not user:
        user = user_repo.find_by_email(email)
        if user:
            from backend.models_mongo import User
            User.objects(id=user.id).update(
                set__google_id=google_id,
                set__avatar_url=avatar_url or user.avatar_url
            )
        else:
            user = user_repo.create_user(
                email=email,
                google_id=google_id,
                name=name,
                avatar_url=avatar_url,
                role="developer",
                email_verified=True,
                is_admin=False,
            )
    else:
        from backend.models_mongo import User
        User.objects(id=user.id).update(set__avatar_url=avatar_url or user.avatar_url)

    user_id = user.id
    log_audit_event("user.google_signin.success", user_id=user_id)

    user_dict = user_repo.get_by_id_str(user_id)
    token = create_access_token(identity=str(user_id))
    resp = jsonify({"user": _user_payload(user_dict)})
    set_access_cookies(resp, token)
    return resp


@auth_bp.route("/github/login/url")
@jwt_required()
def github_login_url():
    oauth_config = _github_oauth_config()
    if not oauth_config:
        return jsonify({
            "error": "GitHub OAuth is not configured. The app administrator must set "
                     "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET."
        }), 503
    client_id, _ = oauth_config
    backend_url = current_app.config.get("BACKEND_URL") or "http://localhost:5000"
    redirect_uri = f"{backend_url.rstrip('/')}/api/auth/github/callback"
    state = _github_state_serializer().dumps({
        "user_id": get_jwt_identity(),
        "nonce": secrets.token_urlsafe(24),
    })
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "scope": "repo read:org workflow",
        "redirect_uri": redirect_uri,
        "state": state,
    })
    return jsonify({"url": url})


@auth_bp.route("/github/login")
@jwt_required()
def github_login():
    response = github_login_url()
    if isinstance(response, tuple):
        return response
    return redirect(response.get_json()["url"])


@auth_bp.route("/github/callback")
def github_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    github_error = request.args.get("error")
    if github_error:
        return _github_frontend_redirect(
            error=request.args.get("error_description") or "GitHub authorization was cancelled."
        )
    if not code or not state:
        return _github_frontend_redirect(error="GitHub returned an incomplete OAuth response.")

    oauth_config = _github_oauth_config()
    if not oauth_config:
        return _github_frontend_redirect(error="GitHub OAuth is not configured on this server.")
    client_id, client_secret = oauth_config

    try:
        state_data = _github_state_serializer().loads(
            state,
            max_age=GITHUB_OAUTH_STATE_MAX_AGE,
        )
    except SignatureExpired:
        return _github_frontend_redirect(error="GitHub connection expired. Please try again.")
    except BadSignature:
        return _github_frontend_redirect(error="Invalid GitHub connection state. Please try again.")

    user_dict = _get_user(state_data.get("user_id"))
    if not user_dict:
        return _github_frontend_redirect(error="The Pipeline.sh user account no longer exists.")

    user_id = user_dict["id"]

    try:
        token_resp = requests.post(
            "https://github.com/login/oauth/access_token",
            json={"client_id": client_id, "client_secret": client_secret, "code": code},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except (requests.RequestException, ValueError):
        logger.exception("GitHub token exchange failed")
        return _github_frontend_redirect(error="GitHub token exchange failed. Please try again.")

    access_token = token_data.get("access_token")
    if not access_token:
        return _github_frontend_redirect(
            error=token_data.get("error_description") or "GitHub did not return an access token."
        )

    try:
        gh_user_resp = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )
        gh_user_resp.raise_for_status()
        gh_user = gh_user_resp.json()
    except (requests.RequestException, ValueError):
        logger.exception("GitHub user lookup failed")
        return _github_frontend_redirect(error="Could not read the connected GitHub account.")

    github_id_value = gh_user.get("id")
    if not github_id_value or not gh_user.get("login"):
        return _github_frontend_redirect(error="GitHub returned an incomplete user profile.")
    github_id = str(github_id_value)
    github_login_name = gh_user.get("login")

    gh_conn_repo = GithubConnectionRepository()
    user_repo = _get_user_repository()

    # Check if this GitHub account is already connected to any user
    existing_connection = gh_conn_repo.find_by_user_and_github_id(user_id, github_id)
    if existing_connection and existing_connection.user_id != user_id:
        return _github_frontend_redirect(
            error="This GitHub account is already connected to another Pipeline.sh user."
        )

    # Check if this GitHub ID is linked to another user
    existing_user = user_repo.find_by_github_id(github_id)
    if existing_user and existing_user.id != user_id:
        return _github_frontend_redirect(
            error="This GitHub account is already connected to another user."
        )

    # Create or update the GitHub connection
    gh_conn_repo.upsert(
        user_id=user_id,
        github_id=github_id,
        login=github_login_name,
        access_token=access_token,
    )

    # Update the user's GitHub ID and avatar
    from backend.models_mongo import User, UserProfile
    User.objects(id=user_id).update(
        set__github_id=github_id,
        set__avatar_url=gh_user.get("avatar_url") or user_dict.get("avatar_url", ""),
    )
    User.objects(id=user_id).update(
        set__profile__github_connected=True,
        set__profile__github_access_token=access_token,
        set__profile__github_login=github_login_name,
    )

    return _github_frontend_redirect(connected="1")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            log_audit_event("user.logout", user_id=int(identity))
    except Exception:
        pass
    resp = jsonify({"message": "Successfully logged out"})
    unset_jwt_cookies(resp)
    return resp


@auth_bp.route("/profile", methods=["PATCH"])
@jwt_required()
def update_profile():
    user_dict = _get_user(get_jwt_identity())
    if not user_dict:
        return jsonify({"error": "Not found"}), 404

    user_id = user_dict["id"]
    data = request.get_json() or {}

    from backend.models_mongo import User, UserProfile

    updates = {}
    profile_updates = {}

    if "notification_email" in data:
        profile_updates["notification_email"] = data["notification_email"]
    if "name" in data:
        updates["name"] = data["name"]

    if updates:
        User.objects(id=user_id).update(set__**updates)
    if profile_updates:
        # UserProfile is embedded in User; route updates through the parent document
        profile_set = {f"set__profile__{k}": v for k, v in profile_updates.items()}
        User.objects(id=user_id).update(**profile_set)

    log_audit_event("user.profile_update", user_id=user_id)

    user_repo = _get_user_repository()
    updated_user = user_repo.get_by_id_str(user_id)
    return jsonify({"user": _user_payload(updated_user)})


@auth_bp.route("/github/disconnect", methods=["POST"])
@jwt_required()
def disconnect_github():
    user_dict = _get_user(get_jwt_identity())
    if not user_dict:
        return jsonify({"error": "Not found"}), 404

    user_id = user_dict["id"]

    from backend.models_mongo import User, UserProfile, GithubConnection

    # Clear GitHub connection from user
    User.objects(id=user_id).update(set__github_id="")

    # Clear profile fields (UserProfile is embedded in User)
    User.objects(id=user_id).update(
        set__profile__github_connected=False,
        set__profile__github_access_token="",
        set__profile__github_login="",
    )

    return jsonify({"message": "GitHub disconnected", "user": _user_payload(user_dict)})
