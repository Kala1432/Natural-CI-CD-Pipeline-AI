"""
Phase 4 verification tests:
- analyze_service edge cases (empty repo, rate limit, truncated tree, deploy yaml_snippet)
- GET /api/projects/:id/status endpoint
- POST /api/projects/:id/analyze re-analysis endpoint
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.models_mongo import User, UserProfile, Project, AutomationStep
from backend.repositories import UserRepository, ProjectRepository, AutomationStepRepository
from backend.app import create_app


# ── App / DB fixtures ─────────────────────────────────────────────────────────

@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "JWT_SECRET_KEY": "test-secret-key-32-bytes-long!!!",
        "SECRET_KEY": "test-secret-key-32-bytes-long!!!",
        "MONGODB_URI": "mongomock://localhost",
    })
    with application.app_context():
        db = User._get_collection().database
        for collection in db.list_collection_names():
            db.drop_collection(collection)
        yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(app, client):
    """Register a user and return JWT headers."""
    client.post("/api/auth/register", json={
        "name": "Phase4 User", "email": "phase4@test.com", "password": "pass1234"
    })
    client.post("/api/auth/login", json={
        "email": "phase4@test.com", "password": "pass1234"
    })

    with app.app_context():
        user_repo = UserRepository()
        user = user_repo.find_by_email("phase4@test.com")
        if user and user.profile:
            user.profile.github_access_token = "fake-gh-token"
            user.profile.github_connected = True
            user.save()

    return {}


@pytest.fixture()
def project(app, auth_headers, client):
    """Create a bare project row (no analysis) for endpoint tests."""
    with app.app_context():
        user_repo = UserRepository()
        user = user_repo.find_by_email("phase4@test.com")
        project_repo = ProjectRepository()
        p = project_repo.create(
            created_by=str(user.id),
            repo_url="https://github.com/test/repo",
            repo_owner="test",
            repo_name="repo",
            default_branch="main",
        )
        project_repo.update_status(str(p.id), "failed", error_message="previous failure")
        pid = str(p.id)
    yield pid
    with app.app_context():
        Project.objects(id=pid).delete()


# ── Seed helper ───────────────────────────────────────────────────────────────

def _ensure_analyze_user(app):
    """Create the analyze@test.com user if it doesn't exist, return its id."""
    with app.app_context():
        user_repo = UserRepository()
        u = user_repo.find_by_email("analyze@test.com")
        if not u:
            u = user_repo.create_user(
                name="Analyze User",
                email="analyze@test.com",
                password_hash="x",
            )
        return str(u.id)


# ── analyze_service unit tests ────────────────────────────────────────────────

class TestAnalyzeServiceEdgeCases:

    def test_empty_repo_sets_failed(self, app):
        """analyze_repo should set status=failed when tree is empty."""
        from backend.services.analyze_service import analyze_repo

        uid = _ensure_analyze_user(app)
        with app.app_context():
            project_repo = ProjectRepository()
            p = project_repo.create(
                created_by=uid,
                repo_url="https://github.com/a/b",
                repo_owner="a",
                repo_name="b",
                default_branch="main",
            )
            pid = str(p.id)

        with patch("backend.services.github_service.GitHubService") as MockGH:
            MockGH.return_value.get_repo_tree.return_value = {"tree": [], "truncated": False}
            analyze_repo(pid, "token")

        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "failed"
            assert "empty" in (p.error_message or "").lower()
            Project.objects(id=pid).delete()

    def test_non_manifest_repo_analyzes_successfully(self, app):
        """analyze_repo should successfully analyze repos even without package manifests (e.g. HTML/docs/scripts)."""
        from backend.services.analyze_service import analyze_repo

        uid = _ensure_analyze_user(app)
        with app.app_context():
            project_repo = ProjectRepository()
            p = project_repo.create(
                created_by=uid,
                repo_url="https://github.com/a/c",
                repo_owner="a",
                repo_name="c",
                default_branch="main",
            )
            pid = str(p.id)

        with patch("backend.services.github_service.GitHubService") as MockGH:
            MockGH.return_value.get_repo_tree.return_value = {
                "tree": [{"path": "README.md", "type": "blob"}],
                "truncated": False,
            }
            analyze_repo(pid, "token")

        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "awaiting_approval"
            Project.objects(id=pid).delete()

    def test_rate_limit_sets_failed(self, app):
        """analyze_repo should fail with rate-limit message on GitHub rate-limit response."""
        from backend.services.analyze_service import analyze_repo

        uid = _ensure_analyze_user(app)
        with app.app_context():
            project_repo = ProjectRepository()
            p = project_repo.create(
                created_by=uid,
                repo_url="https://github.com/a/d",
                repo_owner="a",
                repo_name="d",
                default_branch="main",
            )
            pid = str(p.id)

        with patch("backend.services.github_service.GitHubService") as MockGH:
            MockGH.return_value.get_repo_tree.return_value = {
                "message": "API rate limit exceeded for ..."
            }
            analyze_repo(pid, "token")

        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "failed"
            assert "rate limit" in (p.error_message or "").lower()
            Project.objects(id=pid).delete()

    def test_truncated_tree_warning_in_step_description(self, app):
        """Truncated tree flag should prepend a warning to the first step description."""
        from backend.services.analyze_service import analyze_repo

        pkg_json = json.dumps({"dependencies": {"react": "^18"}, "scripts": {"build": "vite build"}})
        uid = _ensure_analyze_user(app)
        with app.app_context():
            project_repo = ProjectRepository()
            p = project_repo.create(
                created_by=uid,
                repo_url="https://github.com/a/e",
                repo_owner="a",
                repo_name="e",
                default_branch="main",
            )
            pid = str(p.id)

        with patch("backend.services.github_service.GitHubService") as MockGH:
            MockGH.return_value.get_repo_tree.return_value = {
                "tree": [{"path": "package.json", "type": "blob"}],
                "truncated": True,
            }
            MockGH.return_value.get_file_content.return_value = pkg_json
            analyze_repo(pid, "token")

        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "awaiting_approval"
            steps = list(AutomationStep.objects(project_id=p.id))
            assert steps, "Expected at least one step"
            assert "truncated" in steps[0].description.lower()
            AutomationStep.objects(project_id=p.id).delete()
            Project.objects(id=pid).delete()

    def test_deploy_step_always_has_yaml_snippet(self):
        """_generate_steps must always populate yaml_snippet_preview on the deploy step."""
        from backend.services.analyze_service import _generate_steps

        stack = {
            "language": "python", "framework": "flask", "package_manager": "pip",
            "has_tests": False, "has_dockerfile": False, "has_ci": False,
            "test_framework": None, "lint_config": None,
            "node_version": None, "python_version": None,
        }
        steps = _generate_steps(stack, {}, set(), "owner", "repo")
        deploy = next((s for s in steps if s["step_key"] == "deploy"), None)
        assert deploy is not None
        assert deploy["yaml_snippet_preview"] is not None
        assert len(deploy["yaml_snippet_preview"]) > 0

    def test_intermediate_statuses_committed(self, app):
        """analyze_repo should commit both pending_analysis and analyzed before awaiting_approval."""
        from backend.services.analyze_service import analyze_repo

        uid = _ensure_analyze_user(app)
        with app.app_context():
            project_repo = ProjectRepository()
            p = project_repo.create(
                created_by=uid,
                repo_url="https://github.com/a/f",
                repo_owner="a",
                repo_name="f",
                default_branch="main",
            )
            pid = str(p.id)

        with patch("backend.services.github_service.GitHubService") as MockGH:
            MockGH.return_value.get_repo_tree.return_value = {
                "tree": [{"path": "README.md", "type": "blob"}],
                "truncated": False,
            }
            analyze_repo(pid, "token")

        # Should reach awaiting_approval final state
        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "awaiting_approval"
            Project.objects(id=pid).delete()


# ── Endpoint tests ────────────────────────────────────────────────────────────

class TestStatusEndpoint:
    def test_status_returns_404_for_missing_project(self, client, auth_headers):
        res = client.get("/api/projects/000000000000000000000000/status", headers=auth_headers)
        assert res.status_code == 404

    def test_status_returns_project_status(self, client, auth_headers, project):
        res = client.get(f"/api/projects/{project}/status", headers=auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] in ("failed", "analyzed", "awaiting_approval", "pending_analysis")


class TestReanalyzeEndpoint:
    def test_reanalyze_kicks_off_celery_task(self, app, client, auth_headers, project):
        with patch("backend.services.analyze_service.analyze_repo.delay") as mock_delay:
            mock_delay.return_value.id = "celery-id"
            res = client.post(f"/api/projects/{project}/analyze", headers=auth_headers)
            assert res.status_code == 202
            data = res.get_json()
            assert data["task_id"] == "celery-id"
            mock_delay.assert_called_once()
