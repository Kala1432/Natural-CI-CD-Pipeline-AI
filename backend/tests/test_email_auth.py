import pytest

from backend.routes.auth import _otp_hash


@pytest.fixture()
def captured_otps():
    return []


@pytest.fixture()
def app(captured_otps, monkeypatch):
    """Create a test app with EMAIL_VERIFICATION_REQUIRED=True and no mail sending."""
    from backend.app import create_app
    application = create_app({
        "TESTING": True,
        "JWT_SECRET_KEY": "test-jwt-secret-at-least-32-bytes",
        "SECRET_KEY": "test-app-secret-at-least-32-bytes",
        "EMAIL_VERIFICATION_REQUIRED": True,
        "MAIL_SUPPRESS_SEND": False,
        "OTP_RESEND_COOLDOWN_SECONDS": 0,
        "OTP_EXPIRY_MINUTES": 10,
        "OTP_MAX_ATTEMPTS": 3,
        "MONGODB_URI": "mongomock://localhost",
    })

    def fake_send(email, code, purpose):
        captured_otps.append({"email": email, "code": code, "purpose": purpose})

    # Patch the symbols in the module that uses them (auth.py imports them directly)
    monkeypatch.setattr("backend.routes.auth.send_otp_email", fake_send)
    monkeypatch.setattr("backend.routes.auth.email_is_configured", lambda: True)

    with application.app_context():
        # Clean MongoDB collections before each test
        from backend.models_mongo import User
        db = User._get_collection().database
        for collection in db.list_collection_names():
            db.drop_collection(collection)
        yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def get_latest_otp(captured_otps, email, purpose):
    for entry in reversed(captured_otps):
        if entry["email"] == email and entry["purpose"] == purpose:
            return entry["code"]
    return None


def test_registration_requires_valid_email_otp(client, captured_otps):
    registration = client.post("/api/auth/register", json={
        "name": "Verified User",
        "email": "verified@example.com",
        "password": "password123",
    })
    assert registration.status_code == 202
    data = registration.get_json()
    assert data["requires_verification"] is True
    # Verify debug_otp is NOT exposed in response
    assert "debug_otp" not in data

    otp_code = get_latest_otp(captured_otps, "verified@example.com", "verify_email")
    assert otp_code is not None
    assert len(otp_code) == 6
    assert otp_code.isdigit()

    blocked_login = client.post("/api/auth/login", json={
        "email": "verified@example.com",
        "password": "password123",
    })
    assert blocked_login.status_code == 403

    invalid = client.post("/api/auth/verify-email", json={
        "email": "verified@example.com",
        "otp": "000000",
    })
    assert invalid.status_code == 400

    verified = client.post("/api/auth/verify-email", json={
        "email": "verified@example.com",
        "otp": otp_code,
    })
    assert verified.status_code == 200

    reused = client.post("/api/auth/verify-email", json={
        "email": "verified@example.com",
        "otp": otp_code,
    })
    assert reused.status_code == 409


def test_forgot_password_otp_resets_password(client, captured_otps):
    client.post("/api/auth/register", json={
        "name": "Reset User",
        "email": "reset@example.com",
        "password": "old-password",
    })
    reg_otp = get_latest_otp(captured_otps, "reset@example.com", "verify_email")
    client.post("/api/auth/verify-email", json={
        "email": "reset@example.com",
        "otp": reg_otp,
    })

    forgot = client.post("/api/auth/forgot-password", json={
        "email": "reset@example.com",
    })
    assert forgot.status_code == 200
    assert "debug_otp" not in forgot.get_json()

    reset_otp = get_latest_otp(captured_otps, "reset@example.com", "reset_password")
    assert reset_otp is not None

    reset = client.post("/api/auth/reset-password", json={
        "email": "reset@example.com",
        "otp": reset_otp,
        "new_password": "new-password",
    })
    assert reset.status_code == 200

    old_login = client.post("/api/auth/login", json={
        "email": "reset@example.com",
        "password": "old-password",
    })
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", json={
        "email": "reset@example.com",
        "password": "new-password",
    })
    assert new_login.status_code == 200


def test_forgot_password_does_not_reveal_unknown_email(client):
    response = client.post("/api/auth/forgot-password", json={
        "email": "missing@example.com",
    })
    assert response.status_code == 200
    assert "If an account exists" in response.get_json()["message"]
