import pytest

from backend.app import create_app
from backend.db import db


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-jwt-secret-at-least-32-bytes",
        "SECRET_KEY": "test-app-secret-at-least-32-bytes",
        "EMAIL_VERIFICATION_REQUIRED": True,
        "MAIL_SUPPRESS_SEND": True,
        "OTP_RESEND_COOLDOWN_SECONDS": 0,
        "OTP_EXPIRY_MINUTES": 10,
        "OTP_MAX_ATTEMPTS": 3,
    })
    with application.app_context():
        db.create_all()
        yield application
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_registration_requires_valid_email_otp(client):
    registration = client.post("/api/auth/register", json={
        "name": "Verified User",
        "email": "verified@example.com",
        "password": "password123",
    })
    assert registration.status_code == 202
    data = registration.get_json()
    assert data["requires_verification"] is True
    assert len(data["debug_otp"]) == 6

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
        "otp": data["debug_otp"],
    })
    assert verified.status_code == 200
    assert verified.get_json()["access_token"]

    reused = client.post("/api/auth/verify-email", json={
        "email": "verified@example.com",
        "otp": data["debug_otp"],
    })
    assert reused.status_code == 409


def test_forgot_password_otp_resets_password(client):
    registration = client.post("/api/auth/register", json={
        "name": "Reset User",
        "email": "reset@example.com",
        "password": "old-password",
    }).get_json()
    client.post("/api/auth/verify-email", json={
        "email": "reset@example.com",
        "otp": registration["debug_otp"],
    })

    forgot = client.post("/api/auth/forgot-password", json={
        "email": "reset@example.com",
    })
    assert forgot.status_code == 200
    reset_otp = forgot.get_json()["debug_otp"]

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
