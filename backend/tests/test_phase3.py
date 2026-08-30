import pytest
from unittest.mock import patch, MagicMock
from bson import ObjectId

from backend.models_mongo import User, UserProfile, SimulationRun, Project
from backend.repositories import (
    UserRepository,
    ProjectRepository,
    SimulationRunRepository,
)
from backend.app import create_app


@pytest.fixture()
def app():
    """Create app with MongoDB (mongomock) for testing."""
    application = create_app({
        "TESTING": True,
        "JWT_SECRET_KEY": "test-secret-key-32-bytes-long!!!",
        "SECRET_KEY": "test-secret-key-32-bytes-long!!!",
        "MONGODB_URI": "mongomock://localhost",
    })
    with application.app_context():
        # Clean MongoDB collections
        db = User._get_collection().database
        for collection in db.list_collection_names():
            db.drop_collection(collection)
        yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def registered_user(app, client):
    """Register a user via the API and return user info."""
    client.post("/api/auth/register", json={
        "name": "Phase3 User", "email": "phase3@test.com", "password": "pass1234"
    })
    client.post("/api/auth/login", json={
        "email": "phase3@test.com", "password": "pass1234"
    })
    # Return the user record from DB so project creation uses the same user
    with app.app_context():
        user_repo = UserRepository()
        user = user_repo.find_by_email("phase3@test.com")
        # Set GitHub profile info for simulation tests
        if user and user.profile:
            user.profile.github_access_token = "fake-gh-token"
            user.profile.github_connected = True
            user.profile.github_login = "phase3user"
            user.save()
        return user


def _make_project(registered_user, app):
    """Create a project owned by the already-registered user."""
    with app.app_context():
        project_repo = ProjectRepository()
        project = project_repo.create(
            created_by=str(registered_user.id),
            repo_url="https://github.com/test/repo",
            repo_owner="test",
            repo_name="repo",
            default_branch="main",
        )
        project_repo.update_status(str(project.id), "analyzed")
        return str(project.id)


class TestSimulationsAPI:
    @patch("backend.services.simulation_service.run_simulation")
    @patch("backend.services.github_service.GitHubService.get_repo_tree")
    def test_start_simulation_success(self, mock_tree, mock_run_sim, client, registered_user, app):
        # Provide a no-op .delay so the route's `run_simulation.delay(...)` works
        mock_run_sim.delay = MagicMock()
        mock_tree.return_value = {
            "tree": [{"path": "main.py", "type": "blob"}, {"path": "README.md", "type": "blob"}]
        }
        pid = _make_project(registered_user, app)

        res = client.post(f"/api/projects/{pid}/simulate", json={"error_type": "syntax_error"})

        assert res.status_code == 201, f"Got {res.status_code}: {res.get_json()}"
        data = res.get_json()
        assert data["message"] == "Simulation started"
        sim = data["simulation"]
        assert sim["injected_error_type"] == "syntax_error"
        # main.py is in the tree candidates
        assert sim["injected_file"] == "main.py"
        assert sim["status"] == "running"

        mock_run_sim.delay.assert_called_once()

    def test_list_simulations(self, client, registered_user, app):
        pid = _make_project(registered_user, app)

        with app.app_context():
            sim_repo = SimulationRunRepository()
            sim_repo.create(
                project_id=pid,
                injected_error_type="missing_import",
                injected_file="index.js",
                injected_diff="...",
            )
            sim_repo.update_result(pid, status="ai_fixed")

        res = client.get(f"/api/projects/{pid}/simulations")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["simulations"]) >= 1
        assert any(s["injected_error_type"] == "missing_import" for s in data["simulations"])


class TestSimulationService:
    @patch("backend.services.github_service.GitHubService")
    @patch("backend.services.ai_service.AIService")
    @patch("time.sleep", return_value=None)
    def test_run_simulation_full_loop(self, mock_sleep, MockAI, MockGH, registered_user, app):
        from backend.services.simulation_service import run_simulation

        # Setup mocks
        mock_gh = MagicMock()
        mock_gh.create_branch.return_value = {"ref": "refs/heads/sim-branch"}
        mock_gh.get_file_content.return_value = "def hello():\n    print('world')"
        mock_gh.commit_file.return_value = {"commit": {"sha": "123"}}

        # Mock polling: return completed/failure first, then completed/success
        mock_gh.get_workflow_runs.side_effect = [
            {"workflow_runs": [{"id": 42, "status": "completed", "conclusion": "failure"}]},
            {"workflow_runs": [{"id": 43, "status": "completed", "conclusion": "success"}]}
        ]

        mock_gh.get_workflow_run_logs.return_value = "SyntaxError: invalid syntax"
        MockGH.return_value = mock_gh

        mock_ai = MagicMock()
        mock_ai.analyze_logs.return_value = {"debug_advice": "You have a syntax error."}
        mock_ai.generate_code_fix.return_value = "def hello():\n    print('world')\n"
        MockAI.return_value = mock_ai

        pid = _make_project(registered_user, app)
        with app.app_context():
            sim_repo = SimulationRunRepository()
            sim = sim_repo.create(
                project_id=pid,
                injected_error_type="syntax_error",
                injected_file="main.py",
                injected_diff="pending",
            )
            sim_repo.update_result(str(sim.id), status="running")
            sim_id = str(sim.id)

        # Run the simulation task synchronously inside an active app context
        # so _get_app() finds the test app rather than creating a fresh one
        with app.app_context():
            run_simulation(sim_id, "fake-token")

        with app.app_context():
            sim_repo = SimulationRunRepository()
            sim_after = sim_repo.get_by_id(sim_id)
            assert sim_after.status == "ai_fixed"
            assert "SyntaxError" in (sim_after.pipeline_log or "")
            assert "Fixed by AI" in (sim_after.ai_fix_diff or "")
