from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

import pytest

from backend.app import create_app
from backend.db import db
from backend.models import User, UserProfile


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-jwt-secret",
        "SECRET_KEY": "test-app-secret",
        "GITHUB_CLIENT_ID": "github-client-id",
        "GITHUB_CLIENT_SECRET": "github-client-secret",
        "BACKEND_URL": "http://localhost:5000",
        "FRONTEND_URL": "http://localhost:3000",
    })
    with application.app_context():
        db.create_all()
        yield application
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(client):
    response = client.post("/api/auth/register", json={
        "name": "OAuth User",
        "email": "oauth@example.com",
        "password": "password123",
    })
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def _state_from_login_url(client, headers):
    response = client.get("/api/auth/github/login/url", headers=headers)
    assert response.status_code == 200
    query = parse_qs(urlparse(response.get_json()["url"]).query)
    return query["state"][0]


def test_login_url_uses_signed_state(client, auth_headers):
    state = _state_from_login_url(client, auth_headers)
    assert state != "1"
    assert len(state) > 40


def test_callback_rejects_tampered_state(client, auth_headers):
    state = _state_from_login_url(client, auth_headers)
    response = client.get(
        f"/api/auth/github/callback?code=abc&state={state}tampered"
    )
    assert response.status_code == 302
    assert "Invalid+GitHub+connection+state" in response.location


@patch("backend.routes.auth.requests.get")
@patch("backend.routes.auth.requests.post")
def test_callback_connects_current_user_without_jwt_in_url(
    mock_post, mock_get, client, auth_headers, app
):
    state = _state_from_login_url(client, auth_headers)

    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"access_token": "github-user-token"}
    mock_post.return_value = token_response

    user_response = Mock()
    user_response.raise_for_status.return_value = None
    user_response.json.return_value = {
        "id": 12345,
        "login": "octocat",
        "avatar_url": "https://avatars.example/octocat",
    }
    mock_get.return_value = user_response

    response = client.get(
        f"/api/auth/github/callback?code=valid-code&state={state}"
    )
    assert response.status_code == 302
    assert response.location == "http://localhost:3000/auth/github/success?connected=1"
    assert "token=" not in response.location

    with app.app_context():
        user = User.query.filter_by(email="oauth@example.com").one()
        profile = UserProfile.query.filter_by(user_id=user.id).one()
        assert user.github_id == "12345"
        assert profile.github_connected is True
        assert profile.github_login == "octocat"
        assert profile.github_access_token == "github-user-token"
