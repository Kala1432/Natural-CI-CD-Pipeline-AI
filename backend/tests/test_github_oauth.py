from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

import pytest

from backend.app import create_app
from backend.models_mongo import User, UserProfile


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "JWT_SECRET_KEY": "test-jwt-secret-at-least-32-bytes",
        "SECRET_KEY": "test-app-secret-at-least-32-bytes",
        "GITHUB_CLIENT_ID": "github-client-id",
        "GITHUB_CLIENT_SECRET": "github-client-secret",
        "BACKEND_URL": "http://localhost:5000",
        "FRONTEND_URL": "http://localhost:3000",
        "MONGODB_URI": "mongomock://localhost",
    })
    with application.app_context():
        # Clean MongoDB collections before each test
        db = User._get_collection().database
        for collection in db.list_collection_names():
            db.drop_collection(collection)
        yield application


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
    return {}


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
        user = User.objects(email="oauth@example.com").first()
        assert user is not None
        assert user.github_id == "12345"
        # UserProfile is embedded in User — read from user.profile
        assert user.profile is not None
        assert user.profile.github_connected is True
        assert user.profile.github_login == "octocat"
        assert user.profile.github_access_token == "github-user-token"
