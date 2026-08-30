"""
Phase 5 verification tests:
- PATCH /api/projects/:id/steps  — bulk approve/reject
- POST  /api/projects/:id/generate — YAML generation
- workflow_service.build_workflow — YAML content correctness per stack
"""
import pytest
from unittest.mock import patch

from backend.models_mongo import User, UserProfile, Project, AutomationStep, GeneratedWorkflow
from backend.repositories import (
    UserRepository, ProjectRepository,
    AutomationStepRepository, GeneratedWorkflowRepository,
)
from backend.app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
    client.post("/api/auth/register", json={
        "name": "Phase5 User", "email": "phase5@test.com", "password": "pass1234"
    })
    client.post("/api/auth/login", json={
        "email": "phase5@test.com", "password": "pass1234"
    })

    with app.app_context():
        user_repo = UserRepository()
        user = user_repo.find_by_email("phase5@test.com")
        if user and user.profile:
            user.profile.github_access_token = "fake-token"
            user.profile.github_connected = True
            user.save()
    return {}


def _make_project(app, user_email, stack=None, status="awaiting_approval"):
    """Helper: create a project with steps and return (project_id, step_ids)."""
    with app.app_context():
        user_repo = UserRepository()
        user = user_repo.find_by_email(user_email)
        if not user:
            from passlib.hash import argon2
            from backend.models_mongo import User as MongoUser, UserProfile
            user = MongoUser(
                email=user_email,
                password_hash=argon2.hash("pass1234"),
                email_verified=True,
                name=user_email.split("@")[0],
                profile=UserProfile(),
            )
            user.save()
        project_repo = ProjectRepository()
        step_repo = AutomationStepRepository()

        p = project_repo.create(
            created_by=str(user.id),
            repo_url="https://github.com/test/p5repo",
            repo_owner="test",
            repo_name="p5repo",
            default_branch="main",
        )
        project_repo.update_status(str(p.id), status)

        if stack:
            from backend.models_mongo import DetectedStack
            p.detected_stack = DetectedStack(**stack)
            p.save()

        step_data = [
            ("lint",   "Lint",   True),
            ("test",   "Test",   True),
            ("build",  "Build",  False),
            ("deploy", "Deploy", False),
        ]
        step_ids = []
        for key, title, recommended in step_data:
            s = step_repo.create(
                project_id=str(p.id),
                step_key=key,
                title=title,
                description=f"{title} description",
                recommended=recommended,
                yaml_snippet_preview=f"- run: {key}",
            )
            # Recommended ones start pre-approved
            if recommended:
                step_repo.approve(str(s.id))
            step_ids.append(str(s.id))
        return str(p.id), step_ids


# ── PATCH /steps tests ────────────────────────────────────────────────────────

class TestStepApproval:
    def test_bulk_approve_updates_steps(self, client, auth_headers, app):
        pid, sids = _make_project(app, "phase5@test.com")
        payload = [{"id": sid, "approved": True} for sid in sids]
        res = client.patch(f"/api/projects/{pid}/steps", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert all(s["approved"] for s in data["steps"])

    def test_bulk_reject_updates_steps(self, client, auth_headers, app):
        pid, sids = _make_project(app, "phase5@test.com")
        payload = [{"id": sids[0], "approved": False}, {"id": sids[1], "approved": False}]
        res = client.patch(f"/api/projects/{pid}/steps", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        step_map = {s["id"]: s for s in data["steps"]}
        assert step_map[sids[0]]["approved"] is False
        assert step_map[sids[1]]["approved"] is False

    def test_patch_steps_wrong_status_returns_409(self, client, auth_headers, app):
        pid, sids = _make_project(app, "phase5@test.com", status="pending_analysis")
        res = client.patch(f"/api/projects/{pid}/steps",
                           json=[{"id": sids[0], "approved": True}],
                           headers=auth_headers)
        assert res.status_code == 409

    def test_patch_steps_404_for_wrong_user(self, client, app):
        pid, sids = _make_project(app, "phase5@test.com")
        client.post("/api/auth/register", json={
            "name": "Other5", "email": "other5@test.com", "password": "pass1234"
        })
        res2 = client.post("/api/auth/login", json={"email": "other5@test.com", "password": "pass1234"})
        res = client.patch(f"/api/projects/{pid}/steps",
                           json=[{"id": sids[0], "approved": True}])
        assert res.status_code == 404


# ── POST /generate tests ──────────────────────────────────────────────────────

class TestWorkflowGeneration:
    def test_generate_creates_workflow_record(self, client, auth_headers, app):
        pid, sids = _make_project(app, "phase5@test.com", stack={
            "language": "python", "framework": "flask", "package_manager": "pip",
            "has_tests": True, "test_framework": "pytest", "has_dockerfile": False,
            "has_ci": False, "lint_config": None, "node_version": None, "python_version": "3.11",
        })
        # Approve lint + test
        client.patch(f"/api/projects/{pid}/steps",
                     json=[{"id": sids[0], "approved": True}, {"id": sids[1], "approved": True}],
                     headers=auth_headers)

        res = client.post(f"/api/projects/{pid}/generate", headers=auth_headers)
        assert res.status_code == 201
        wf = res.get_json()["workflow"]
        assert wf["yaml_content"]
        assert wf["filename"] == ".github/workflows/hifi-ci.yml"
        assert wf["pr_status"] == "draft"

        with app.app_context():
            wf_repo = GeneratedWorkflowRepository()
            stored = wf_repo.latest_for_project(pid)
            assert stored is not None
            assert "test" in (stored.yaml_content or "")

    def test_generate_400_when_no_steps_approved(self, client, auth_headers, app):
        pid, sids = _make_project(app, "phase5@test.com")
        # Reject all
        client.patch(f"/api/projects/{pid}/steps",
                     json=[{"id": sid, "approved": False} for sid in sids],
                     headers=auth_headers)
        res = client.post(f"/api/projects/{pid}/generate", headers=auth_headers)
        assert res.status_code == 400

    def test_generate_replaces_previous_draft(self, client, auth_headers, app):
        pid, sids = _make_project(app, "phase5@test.com", stack={
            "language": "javascript", "framework": "react", "package_manager": "npm",
            "has_tests": True, "test_framework": "jest", "has_dockerfile": False,
            "has_ci": False, "lint_config": None, "node_version": "20", "python_version": None,
        })
        client.patch(f"/api/projects/{pid}/steps",
                     json=[{"id": sids[0], "approved": True}], headers=auth_headers)
        client.post(f"/api/projects/{pid}/generate", headers=auth_headers)
        client.post(f"/api/projects/{pid}/generate", headers=auth_headers)

        with app.app_context():
            from backend.repositories import to_oid
            wf_repo = GeneratedWorkflowRepository()
            drafts = list(wf_repo.document_class.objects(
                project_id=to_oid(pid),
                pr_status="draft"
            ))
            assert len(drafts) == 1  # old draft replaced

    def test_generate_409_wrong_status(self, client, auth_headers, app):
        pid, sids = _make_project(app, "phase5@test.com", status="pending_analysis")
        res = client.post(f"/api/projects/{pid}/generate", headers=auth_headers)
        assert res.status_code == 409


# ── workflow_service unit tests ───────────────────────────────────────────────

class TestWorkflowService:
    def _make_steps(self, keys):
        steps = []
        for k in keys:
            s = type("Step", (), {"step_key": k})()
            steps.append(s)
        return steps

    def _make_project_obj(self, stack, repo_name="myrepo", branch="main"):
        p = type("Project", (), {
            "detected_stack": stack,
            "repo_name": repo_name,
            "default_branch": branch,
        })()
        return p

    def test_python_flask_yaml_contains_pytest(self):
        from backend.services.workflow_service import build_workflow
        stack = {"language": "python", "framework": "flask", "package_manager": "pip",
                 "test_framework": "pytest", "lint_config": None, "node_version": None,
                 "python_version": "3.11", "has_dockerfile": False}
        p = self._make_project_obj(stack)
        yaml_out = build_workflow(p, self._make_steps(["test"]))
        assert "pytest" in yaml_out
        assert "setup-python" in yaml_out

    def test_node_react_yaml_contains_npm_ci(self):
        from backend.services.workflow_service import build_workflow
        stack = {"language": "javascript", "framework": "react", "package_manager": "npm",
                 "test_framework": "jest", "lint_config": None, "node_version": "20",
                 "python_version": None, "has_dockerfile": False}
        p = self._make_project_obj(stack)
        yaml_out = build_workflow(p, self._make_steps(["test", "build"]))
        assert "npm ci" in yaml_out
        assert "setup-node" in yaml_out
        assert "npm run build" in yaml_out

    def test_docker_build_step_included(self):
        from backend.services.workflow_service import build_workflow
        stack = {"language": "python", "framework": None, "package_manager": "pip",
                 "test_framework": None, "lint_config": None, "node_version": None,
                 "python_version": "3.11", "has_dockerfile": True}
        p = self._make_project_obj(stack)
        yaml_out = build_workflow(p, self._make_steps(["docker_build"]))
        assert "docker build" in yaml_out

    def test_deploy_step_has_if_condition(self):
        from backend.services.workflow_service import build_workflow
        stack = {"language": "python", "framework": None, "package_manager": "pip",
                 "test_framework": None, "lint_config": None, "node_version": None,
                 "python_version": "3.11", "has_dockerfile": False}
        p = self._make_project_obj(stack, branch="main")
        yaml_out = build_workflow(p, self._make_steps(["deploy"]))
        assert "refs/heads/main" in yaml_out

    def test_go_yaml_contains_go_test(self):
        from backend.services.workflow_service import build_workflow
        stack = {"language": "go", "framework": None, "package_manager": "go modules",
                 "test_framework": "go test", "lint_config": None, "node_version": None,
                 "python_version": None, "has_dockerfile": False}
        p = self._make_project_obj(stack)
        yaml_out = build_workflow(p, self._make_steps(["test", "build"]))
        assert "go test ./..." in yaml_out
        assert "go build ./..." in yaml_out

    def test_workflow_name_includes_repo_name(self):
        from backend.services.workflow_service import build_workflow
        stack = {"language": "python", "framework": None, "package_manager": "pip",
                 "test_framework": None, "lint_config": None, "node_version": None,
                 "python_version": "3.11", "has_dockerfile": False}
        p = self._make_project_obj(stack, repo_name="awesome-app")
        yaml_out = build_workflow(p, self._make_steps(["build"]))
        assert "awesome-app" in yaml_out


class TestPublishWorkflowEndpoint:
    @patch("backend.services.github_service.GitHubService.commit_workflow_file")
    def test_publish_commit_success(self, mock_commit, client, auth_headers, app):
        mock_commit.return_value = {"html_url": "https://github.com/test/repo/commit/123"}

        pid, sids = _make_project(app, "phase5@test.com", stack={
            "language": "python", "framework": "flask", "package_manager": "pip",
            "has_tests": True, "test_framework": "pytest", "has_dockerfile": False,
            "has_ci": False, "lint_config": None, "node_version": None, "python_version": "3.11",
        })

        client.patch(f"/api/projects/{pid}/steps",
                     json=[{"id": sids[0], "approved": True}],
                     headers=auth_headers)
        client.post(f"/api/projects/{pid}/generate", headers=auth_headers)

        res = client.post(f"/api/projects/{pid}/publish", json={
            "method": "commit",
            "commit_message": "Add ci workflow"
        }, headers=auth_headers)

        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["workflow"]["pr_status"] == "merged"

        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "pr_merged"
            wf_repo = GeneratedWorkflowRepository()
            wf = wf_repo.latest_for_project(pid)
            assert wf.pr_status == "merged"
            assert wf.pr_url == "https://github.com/test/repo/commit/123"

    @patch("backend.services.github_service.GitHubService.create_branch")
    @patch("backend.services.github_service.GitHubService.commit_workflow_file")
    @patch("backend.services.github_service.GitHubService.create_pull_request")
    def test_publish_pr_success(self, mock_pr, mock_commit, mock_branch, client, auth_headers, app):
        mock_branch.return_value = {"ref": "refs/heads/hifi-ci-setup"}
        mock_commit.return_value = {"html_url": "https://github.com/test/repo/commit/123"}
        mock_pr.return_value = {"html_url": "https://github.com/test/repo/pull/1", "number": 1}

        pid, sids = _make_project(app, "phase5@test.com", stack={
            "language": "python", "framework": "flask", "package_manager": "pip",
            "has_tests": True, "test_framework": "pytest", "has_dockerfile": False,
            "has_ci": False, "lint_config": None, "node_version": None, "python_version": "3.11",
        })

        client.patch(f"/api/projects/{pid}/steps",
                     json=[{"id": sids[0], "approved": True}],
                     headers=auth_headers)
        client.post(f"/api/projects/{pid}/generate", headers=auth_headers)

        res = client.post(f"/api/projects/{pid}/publish", json={
            "method": "pr",
            "commit_message": "Add ci workflow",
            "branch_name": "my-pr-branch"
        }, headers=auth_headers)

        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        assert data["workflow"]["pr_status"] == "open"
        assert data["workflow"]["pr_number"] == 1

        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "pr_created"

    @patch("backend.services.github_service.GitHubService.get_existing_pull_request")
    @patch("backend.services.github_service.GitHubService.create_branch")
    @patch("backend.services.github_service.GitHubService.commit_workflow_file")
    @patch("backend.services.github_service.GitHubService.create_pull_request")
    def test_publish_pr_existing_pr_returns_success(
        self, mock_pr, mock_commit, mock_branch, mock_existing_pr, client, auth_headers, app
    ):
        mock_branch.return_value = {"ref": "refs/heads/hifi-ci-setup"}
        mock_commit.return_value = {"html_url": "https://github.com/test/repo/commit/123"}
        mock_pr.return_value = {"error": "A pull request already exists.", "status_code": 422}
        mock_existing_pr.side_effect = [None, {"html_url": "https://github.com/test/repo/pull/2", "number": 2}]

        pid, sids = _make_project(app, "phase5@test.com", stack={
            "language": "python", "framework": "flask", "package_manager": "pip",
            "has_tests": True, "test_framework": "pytest", "has_dockerfile": False,
            "has_ci": False, "lint_config": None, "node_version": None, "python_version": "3.11",
        })

        client.patch(f"/api/projects/{pid}/steps",
                     json=[{"id": sids[0], "approved": True}],
                     headers=auth_headers)
        client.post(f"/api/projects/{pid}/generate", headers=auth_headers)

        res = client.post(f"/api/projects/{pid}/publish", json={
            "method": "pr",
            "commit_message": "Add ci workflow",
            "branch_name": "hifi-ci-setup"
        }, headers=auth_headers)

        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["workflow"]["pr_status"] == "open"
        assert data["workflow"]["pr_number"] == 2
        assert "open on github" in data["message"].lower()

        with app.app_context():
            p = Project.objects(id=pid).first()
            assert p.status == "pr_created"
