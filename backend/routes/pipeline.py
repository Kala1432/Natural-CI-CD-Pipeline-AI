from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.repositories import (
    UserRepository,
    PipelineRepository,
    WorkflowLogRepository,
    RepositoryRepository,
)
from backend.services.ai_service import AIService

pipeline_bp = Blueprint("pipeline", __name__)


def _get_user_pipeline_ids(user_id) -> list:
    """Get all repository IDs owned by a user, then pipeline IDs for those repos."""
    repo_repo = RepositoryRepository()
    pipeline_repo = PipelineRepository()
    user_repos = repo_repo.find_by_user(user_id)
    all_pipelines = []
    for repo in user_repos:
        repo_dict = repo.to_dict() if hasattr(repo, 'to_dict') else repo
        pipelines = pipeline_repo.find_by_repository(repo_dict["id"])
        all_pipelines.extend(pipelines)
    return all_pipelines


@pipeline_bp.route("/trigger", methods=["POST"])
@jwt_required()
def trigger_pipeline():
    data = request.get_json() or {}
    repo_id = data.get("repository_id")
    branch = data.get("branch", "main")
    stage = data.get("stage", "development")

    pipeline_repo = PipelineRepository()
    pipeline = pipeline_repo.create(
        repository_id=repo_id,
        name=f"CI/CD - {branch}",
        status="running",
        stage=stage,
        branch=branch,
    )
    return jsonify({"pipeline": {"id": str(pipeline.id), "status": pipeline.status, "stage": pipeline.stage}}), 201


@pipeline_bp.route("/<pipeline_id>/logs", methods=["GET"])
@jwt_required()
def fetch_logs(pipeline_id):
    log_repo = WorkflowLogRepository()
    logs = log_repo.find_by_pipeline(pipeline_id)
    result = [
        {
            "step_name": log.step_name,
            "status": log.status,
            "message": log.message,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        }
        for log in logs
    ]
    return jsonify({"logs": result})


@pipeline_bp.route("/analyze", methods=["POST"])
@jwt_required()
def analyze_pipeline():
    data = request.get_json() or {}
    log_text = data.get("log_text", "")
    ai = AIService()
    report = ai.analyze_logs(log_text)
    return jsonify({"report": report})


@pipeline_bp.route("/history", methods=["GET"])
@jwt_required()
def pipeline_history():
    user_id = get_jwt_identity()
    user_repo = UserRepository()
    user = user_repo.get_by_id_str(user_id)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    pipelines = _get_user_pipeline_ids(user_id)
    # Sort by triggered_at descending, take 20
    pipelines.sort(key=lambda p: p.triggered_at or p.created_at, reverse=True)
    result = [
        {
            "id": str(p.id),
            "status": p.status,
            "stage": p.stage,
            "branch": p.branch,
            "triggered_at": p.triggered_at.isoformat() if p.triggered_at else None,
        }
        for p in pipelines[:20]
    ]
    return jsonify({"pipelines": result})
