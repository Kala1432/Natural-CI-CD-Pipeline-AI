import pytest
from unittest.mock import patch
from bson import ObjectId

from backend.models_mongo import Project
from backend.repositories import (
    ProjectRepository,
    DeploymentRepository,
    CloudDeploymentRepository,
    UserRepository,
)
from backend.app import create_app
from backend.db import db as _db  # legacy import kept for compatibility; not used


@pytest.fixture()
def app():
    """Override parent fixture to ensure a clean mongomock DB per test."""
    application = create_app({
        "TESTING": True,
        "JWT_SECRET_KEY": "test-secret-key-32-bytes-long!!!",
        "SECRET_KEY": "test-secret-key-32-bytes-long!!!",
        "MONGODB_URI": "mongomock://localhost",
    })
    with application.app_context():
        # Clean MongoDB collections
        from backend.models_mongo import User
        mong_db = User._get_collection().database
        for collection in mong_db.list_collection_names():
            mong_db.drop_collection(collection)
        yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(app, client):
    client.post("/api/auth/register", json={
        "name": "DeployUser", "email": "p5@test.com", "password": "pass1234"
    })
    client.post("/api/auth/login", json={
        "email": "p5@test.com", "password": "pass1234"
    })
    return {}


def test_start_deployment_endpoint(app, client, auth_headers):
    """Test that starting a deployment kicks off a Celery task."""
    with app.app_context():
        user_repo = UserRepository()
        user = user_repo.find_by_email("p5@test.com")
        project_repo = ProjectRepository()
        project = project_repo.create(
            created_by=str(user.id),
            repo_url="https://github.com/test/test",
            repo_owner="test",
            repo_name="test",
            default_branch="main",
        )
        project_repo.update_status(str(project.id), "pr_merged")
        pid = str(project.id)

    with patch("backend.routes.deploy.run_deployment.delay") as mock_delay:
        mock_delay.return_value.id = "mock-task-id"
        res = client.post(f"/api/deploy/projects/{pid}", json={"environment": "production"}, headers=auth_headers)
        assert res.status_code == 202
        assert res.get_json()["task_id"] == "mock-task-id"


def test_get_deployments_endpoint(app, client, auth_headers):
    """Test that the deployments list endpoint returns deployment records."""
    with app.app_context():
        user_repo = UserRepository()
        user = user_repo.find_by_email("p5@test.com")
        project_repo = ProjectRepository()
        project = project_repo.create(
            created_by=str(user.id),
            repo_url="https://github.com/test/test2",
            repo_owner="test",
            repo_name="test2",
            default_branch="main",
        )
        project_repo.update_status(str(project.id), "pr_merged")
        project = project_repo.get_by_id(str(project.id))

        # Need a pipeline first to satisfy the foreign key on deployment
        from backend.repositories import PipelineRepository, RepositoryRepository
        # Create a Repository record so the pipeline can reference it
        repo_repo = RepositoryRepository()
        from backend.models_mongo import User as MongoUser
        user = MongoUser.objects(email="p5@test.com").first()
        repo = repo_repo.create(
            user_id=str(user.id),
            github_repo_id="12345",
            name="test",
            full_name="test/test",
        )
        pipeline_repo = PipelineRepository()
        pipeline = pipeline_repo.create(
            repository_id=str(repo.id),
            name="test-pipeline",
            status="running",
            stage="production",
        )

        deploy_repo = DeploymentRepository()
        d = deploy_repo.create(
            pipeline_id=str(pipeline.id),
            environment="production",
            status="running",
        )

        cloud_repo = CloudDeploymentRepository()
        cloud_repo.create(
            deployment_id=str(d.id),
            aws_instance_id="i-mock-123",
            status="running",
        )

    res = client.get("/api/deploy/all", headers=auth_headers)
    assert res.status_code == 200
    deps = res.get_json()["deployments"]
    assert len(deps) >= 1
    assert deps[0]["status"] == "running"
    assert deps[0]["instance_id"] == "i-mock-123"
