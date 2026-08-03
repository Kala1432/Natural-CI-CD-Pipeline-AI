import logging
import os
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, url_for
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from backend.db import db
from backend.models import EmailOTP, GithubConnection, User, UserProfile
from backend.services.email_service import email_is_configured, send_otp_email

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)
GITHUB_OAUTH_STATE_SALT = "github-oauth-state"
GITHUB_OAUTH_STATE_MAX_AGE = 10 * 60
OTP_PURPOSES = ("verify_email", "reset_password")


def _user_payload(user: User) -> dict:
    profile = user.profile
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "github_connected": profile.github_connected if profile else False,
        "github_login": profile.github_login if profile else None,
        "notification_email": profile.notification_email if profile else user.email,
    }


def _ensure_profile(user: User) -> UserProfile:
    if not user.profile:
        profile = UserProfile(
            user_id=user.id,
            github_connected=False,
            notification_email=user.email,
        )
        db.session.add(profile)
        db.session.commit()
    return user.profile


def _get_user(user_id_str) -> User | None:
    try:
        return db.session.get(User, int(user_id_str))
    except (TypeError, ValueError):
        return None


def _github_oauth_config():
    client_id = current_app.config.get("GITHUB_CLIENT_ID", "").strip()
    client_secret = current_app.config.get("GITHUB_CLIENT_SECRET", "").strip()
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


def _send_user_otp(user, purpose, enforce_cooldown=False):
    if purpose not in OTP_PURPOSES:
        raise ValueError("Invalid OTP purpose")

    now = datetime.utcnow()
    latest = EmailOTP.query.filter_by(
        user_id=user.id,
        purpose=purpose,
    ).order_by(EmailOTP.created_at.desc()).first()
    cooldown = current_app.config["OTP_RESEND_COOLDOWN_SECONDS"]
    if (
        enforce_cooldown
        and latest
        and (now - latest.created_at).total_seconds() < cooldown
    ):
        remaining = cooldown - int((now - latest.created_at).total_seconds())
        return None, max(1, remaining)

    if not current_app.config.get("MAIL_SUPPRESS_SEND") and not email_is_configured():
        raise RuntimeError(
            "Email delivery is not configured. The administrator must configure Gmail SMTP."
        )

    EmailOTP.query.filter_by(
        user_id=user.id,
        purpose=purpose,
        consumed_at=None,
    ).update({"consumed_at": now})

    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = EmailOTP(
        user_id=user.id,
        purpose=purpose,
        code_hash=_otp_hash(user.id, purpose, code),
        attempts=0,
        expires_at=now + timedelta(
            minutes=current_app.config["OTP_EXPIRY_MINUTES"]
        ),
    )
    db.session.add(otp)
    db.session.commit()

    if not current_app.config.get("MAIL_SUPPRESS_SEND"):
        try:
            send_otp_email(user.email, code, purpose)
        except Exception:
            db.session.delete(otp)
            db.session.commit()
            raise
    return code, None


def _consume_user_otp(user, purpose, code):
    otp = EmailOTP.query.filter_by(
        user_id=user.id,
        purpose=purpose,
        consumed_at=None,
    ).order_by(EmailOTP.created_at.desc()).first()
    now = datetime.utcnow()
    if not otp or otp.expires_at < now:
        return False, "The code is invalid or has expired."
    if otp.attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        return False, "Too many incorrect attempts. Request a new code."

    if not hmac.compare_digest(
        otp.code_hash,
        _otp_hash(user.id, purpose, str(code).strip()),
    ):
        otp.attempts += 1
        db.session.commit()
        return False, "The code is invalid or has expired."

    otp.consumed_at = now
    db.session.commit()
    return True, None


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
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    verification_required = current_app.config["EMAIL_VERIFICATION_REQUIRED"]
    if (
        verification_required
        and not current_app.config.get("MAIL_SUPPRESS_SEND")
        and not email_is_configured()
    ):
        verification_required = False

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        name=name or email.split("@")[0],
        role="developer",
        email_verified=not verification_required,
    )
    db.session.add(user)
    db.session.flush()

    db.session.add(UserProfile(user_id=user.id, github_connected=False, notification_email=email))
    db.session.commit()

    if verification_required:
        try:
            debug_code, _ = _send_user_otp(user, "verify_email")
        except Exception:
            logger.exception("Registration OTP delivery failed")
            try:
                db.session.rollback()
                user_to_del = db.session.get(User, user.id)
                if user_to_del:
                    db.session.delete(user_to_del)
                    db.session.commit()
            except Exception:
                db.session.rollback()
            return jsonify({"error": "Could not send the verification email. Please try again."}), 502
        response = {
            "message": "Verification code sent.",
            "email": user.email,
            "requires_verification": True,
        }
        if current_app.config.get("TESTING") and current_app.config.get("MAIL_SUPPRESS_SEND"):
            response["debug_otp"] = debug_code
        return jsonify(response), 202

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": _user_payload(user)}), 201


@auth_bp.route("/verify-email", methods=["POST"])
def verify_email():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    code = str(data.get("otp", "")).strip()
    user = User.query.filter_by(email=email).first()
    if not user or not code:
        return jsonify({"error": "A valid email and verification code are required"}), 400
    if user.email_verified:
        return jsonify({"error": "This email is already verified"}), 409

    valid, error = _consume_user_otp(user, "verify_email", code)
    if not valid:
        return jsonify({"error": error}), 400

    user.email_verified = True
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": _user_payload(user)})


@auth_bp.route("/resend-verification", methods=["POST"])
def resend_verification():
    email = (request.get_json() or {}).get("email", "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user or user.email_verified:
        return jsonify({"message": "If verification is pending, a code will be sent."})
    try:
        debug_code, retry_after = _send_user_otp(
            user, "verify_email", enforce_cooldown=True
        )
    except Exception:
        logger.exception("Verification OTP resend failed")
        return jsonify({"error": "Could not send the verification email. Please try again."}), 502
    if retry_after:
        return jsonify({
            "error": f"Please wait {retry_after} seconds before requesting another code.",
            "retry_after": retry_after,
        }), 429
    response = {"message": "Verification code sent."}
    if current_app.config.get("TESTING") and current_app.config.get("MAIL_SUPPRESS_SEND"):
        response["debug_otp"] = debug_code
    return jsonify(response)


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = (request.get_json() or {}).get("email", "").strip().lower()
    user = User.query.filter_by(email=email).first()
    response = {
        "message": "If an account exists for that email, a password reset code has been sent."
    }
    if not user or not user.email_verified:
        return jsonify(response)
    try:
        debug_code, retry_after = _send_user_otp(
            user, "reset_password", enforce_cooldown=True
        )
    except Exception:
        logger.exception("Password reset OTP delivery failed")
        return jsonify({"error": "Could not send the password reset email. Please try again."}), 502
    if retry_after:
        return jsonify({
            "error": f"Please wait {retry_after} seconds before requesting another code.",
            "retry_after": retry_after,
        }), 429
    if current_app.config.get("TESTING") and current_app.config.get("MAIL_SUPPRESS_SEND"):
        response["debug_otp"] = debug_code
    return jsonify(response)


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    code = str(data.get("otp", "")).strip()
    new_password = data.get("new_password", "")
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    user = User.query.filter_by(email=email).first()
    if not user or not code:
        return jsonify({"error": "The code is invalid or has expired."}), 400

    valid, error = _consume_user_otp(user, "reset_password", code)
    if not valid:
        return jsonify({"error": error}), 400
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({"message": "Password reset successfully. You can now sign in."})


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401
    if current_app.config["EMAIL_VERIFICATION_REQUIRED"] and not user.email_verified:
        return jsonify({
            "error": "Verify your email before signing in.",
            "requires_verification": True,
        }), 403

    _ensure_profile(user)
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": _user_payload(user)})


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = _get_user(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404
    _ensure_profile(user)
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
        return jsonify({"error": "Invalid Google token"}), 401

    info = resp.json()
    google_id = info.get("sub")
    email = info.get("email", "").lower()
    name = info.get("name", "")
    avatar_url = info.get("picture", "")

    if not google_id or not email:
        return jsonify({"error": "Google token missing required fields"}), 400

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
            user.avatar_url = avatar_url or user.avatar_url
        else:
            user = User(
                email=email,
                google_id=google_id,
                name=name,
                avatar_url=avatar_url,
                role="developer",
                email_verified=True,
            )
            db.session.add(user)
            db.session.flush()
    else:
        user.avatar_url = avatar_url or user.avatar_url

    _ensure_profile(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": _user_payload(user)})


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

    user = _get_user(state_data.get("user_id"))
    if not user:
        return _github_frontend_redirect(error="The Pipeline.sh user account no longer exists.")

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

    # Check if this GitHub account is already connected to any user
    existing_connection = GithubConnection.query.filter_by(github_id=github_id).first()
    if existing_connection and existing_connection.user_id != user.id:
        # GitHub account is connected to another user
        return _github_frontend_redirect(
            error="This GitHub account is already connected to another Pipeline.sh user."
        )

    # Check if this user already has this GitHub account connected via user.github_id
    user_has_connection = User.query.filter(User.github_id == github_id, User.id != user.id).first()
    if user_has_connection:
        return _github_frontend_redirect(
            error="This GitHub account is already connected to another user."
        )

    # Link this GitHub account to the current user
    # Use new GithubConnection model for multi-account support
    profile = _ensure_profile(user)

    # Create a new GithubConnection record for this GitHub account
    github_connection = GithubConnection(
        user_id=user.id,
        github_id=github_id,
        access_token=access_token,
        login=github_login_name,
    )
    db.session.add(github_connection)

    # Also update the old user.github_id for backward compatibility
    user.github_id = github_id
    user.avatar_url = gh_user.get("avatar_url") or user.avatar_url

    # Update profile for backward compatibility
    profile.github_connected = True
    profile.github_access_token = access_token
    profile.github_login = github_login_name

    db.session.commit()

    return _github_frontend_redirect(connected="1")


@auth_bp.route("/profile", methods=["PATCH"])
@jwt_required()
def update_profile():
    user = _get_user(get_jwt_identity())
    if not user:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json() or {}
    profile = _ensure_profile(user)

    if "notification_email" in data:
        profile.notification_email = data["notification_email"]
    if "name" in data:
        user.name = data["name"]

    db.session.commit()
    return jsonify({"user": _user_payload(user)})


@auth_bp.route("/github/disconnect", methods=["POST"])
@jwt_required()
def disconnect_github():
    user = _get_user(get_jwt_identity())
    if not user:
        return jsonify({"error": "Not found"}), 404

    profile = _ensure_profile(user)
    profile.github_connected = False
    profile.github_access_token = None
    profile.github_login = None
    user.github_id = None
    db.session.commit()
    return jsonify({"message": "GitHub disconnected", "user": _user_payload(user)})
