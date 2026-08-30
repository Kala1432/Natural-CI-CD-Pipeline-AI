import pytest
from passlib.hash import argon2

from backend.app import create_app
from backend.models_mongo import User, AuditLog


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-jwt-secret-at-least-32-bytes-long",
        "SECRET_KEY": "test-app-secret-at-least-32-bytes-long",
        "EMAIL_VERIFICATION_REQUIRED": False,
        "MAIL_SUPPRESS_SEND": True,
        "MONGODB_URI": "mongomock://localhost",
    })
    with application.app_context():
        # Seed an admin and a regular user
        admin = User(
            email="admin@example.com",
            password_hash=argon2.hash("adminpassword123"),
            name="Admin User",
            role="admin",
            is_admin=True,
            email_verified=True,
        )
        developer = User(
            email="dev@example.com",
            password_hash=argon2.hash("devpassword123"),
            name="Dev User",
            role="developer",
            is_admin=False,
            email_verified=True,
        )
        admin.save()
        developer.save()

        yield application

        # Clean up
        User.objects().delete()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_rbac_admin_stats_unauthenticated(client):
    res = client.get("/api/admin/stats")
    assert res.status_code == 401


def test_rbac_admin_stats_developer_forbidden(client):
    login = client.post("/api/auth/login", json={
        "email": "dev@example.com",
        "password": "devpassword123",
    })
    assert login.status_code == 200

    res = client.get("/api/admin/stats")
    assert res.status_code == 403
    assert "Forbidden" in res.get_json()["error"]


def test_rbac_admin_stats_allowed_for_admin(client, app):
    login = client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "adminpassword123",
    })
    assert login.status_code == 200

    res = client.get("/api/admin/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert "total_users" in data
    assert data["total_users"] == 2


def test_audit_logs_recorded_and_viewable_by_admin(client, app):
    # Dev attempts login with wrong password
    client.post("/api/auth/login", json={
        "email": "dev@example.com",
        "password": "wrongpassword",
    })

    # Admin logs in
    client.post("/api/auth/login", json={
        "email": "admin@example.com",
        "password": "adminpassword123",
    })

    # Admin fetches audit logs
    res = client.get("/api/admin/audit-logs")
    assert res.status_code == 200
    logs = res.get_json()["audit_logs"]
    assert len(logs) > 0
    actions = [l["action"] for l in logs]
    assert "user.login.failed" in actions
    assert "user.login.success" in actions


def test_audit_log_helper_direct(app):
    from bson import ObjectId
    with app.app_context():
        entry = AuditLog(
            action="custom.security.event",
            user_id=ObjectId(),
            resource_type="pipeline",
            resource_id="101",
            details={"ip": "127.0.0.1"},
            status="success",
        )
        entry.save()
        assert entry.id is not None
        assert entry.action == "custom.security.event"

        # Query back
        queried = AuditLog.objects(action="custom.security.event").first()
        assert queried is not None
        assert queried.resource_id == "101"
        assert queried.action == "custom.security.event"


def test_google_signin_validations(client, app, monkeypatch):
    import time
    from unittest.mock import Mock

    google_client_id = app.config.get("GOOGLE_CLIENT_ID") or "google-test-client-id"

    # Case 1: Invalid issuer
    mock_resp = Mock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "sub": "g12345",
        "email": "googleuser@example.com",
        "name": "Google User",
        "iss": "https://evil.com",
        "aud": google_client_id,
        "exp": int(time.time()) + 3600,
        "email_verified": True,
    }
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: mock_resp)

    res = client.post("/api/auth/google", json={"id_token": "dummy"})
    assert res.status_code == 401
    assert "issuer" in res.get_json()["error"]

    # Case 2: Expired token
    mock_resp.json.return_value = {
        "sub": "g12345",
        "email": "googleuser@example.com",
        "name": "Google User",
        "iss": "https://accounts.google.com",
        "aud": google_client_id,
        "exp": int(time.time()) - 100,
        "email_verified": True,
    }
    res = client.post("/api/auth/google", json={"id_token": "dummy"})
    assert res.status_code == 401
    assert "expired" in res.get_json()["error"]

    # Case 3: Email not verified
    mock_resp.json.return_value = {
        "sub": "g12345",
        "email": "googleuser@example.com",
        "name": "Google User",
        "iss": "https://accounts.google.com",
        "aud": google_client_id,
        "exp": int(time.time()) + 3600,
        "email_verified": False,
    }
    res = client.post("/api/auth/google", json={"id_token": "dummy"})
    assert res.status_code == 401
    assert "not verified" in res.get_json()["error"]

    # Case 4: Valid token success
    mock_resp.json.return_value = {
        "sub": "g12345",
        "email": "googleuser@example.com",
        "name": "Google User",
        "iss": "https://accounts.google.com",
        "aud": google_client_id,
        "exp": int(time.time()) + 3600,
        "email_verified": True,
    }
    res = client.post("/api/auth/google", json={"id_token": "dummy"})
    assert res.status_code == 200
    assert res.get_json()["user"]["email"] == "googleuser@example.com"


def test_config_security_defaults(monkeypatch):
    import importlib
    import dotenv
    from backend.config import Config
    assert Config.JWT_COOKIE_CSRF_PROTECT is True
    assert Config.JWT_COOKIE_HTTPONLY is True
    assert Config.GITHUB_WEBHOOK_SECRET != "secret"
    assert Config.AWS_DEPLOYMENT_MODE in ("simulation", "real")

    # Test random fallback generation when env var is absent
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    import backend.config
    importlib.reload(backend.config)
    assert backend.config.Config.GITHUB_WEBHOOK_SECRET != "secret"
    assert len(backend.config.Config.GITHUB_WEBHOOK_SECRET) >= 32