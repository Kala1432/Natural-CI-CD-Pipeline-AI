from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.repositories import (
    ProjectRepository,
    DeploymentRepository,
    CloudDeploymentRepository,
    ErrorReportRepository,
)
from backend.services.deployment_service import run_deployment
from backend.services.audit_service import log_audit_event

deploy_bp = Blueprint("deploy", __name__)

@deploy_bp.route("/projects/<project_id>", methods=["POST"])
@jwt_required()
def start_deployment(project_id):
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json() or {}
    environment = data.get("environment", "staging")

    # Trigger async deployment via Celery
    task = run_deployment.delay(project_id, environment)

    log_audit_event(
        action="deployment.triggered",
        user_id=user_id,
        resource_type="project",
        resource_id=project_id,
        details={"environment": environment, "task_id": task.id},
    )

    return jsonify({"message": "Deployment started", "task_id": task.id}), 202


@deploy_bp.route("/all", methods=["GET"])
@jwt_required()
def get_all_deployments():
    # Fetch all deployments, order by latest
    deploy_repo = DeploymentRepository()
    cloud_repo = CloudDeploymentRepository()
    err_repo = ErrorReportRepository()

    deployments = deploy_repo.list_recent(limit=20)

    result = []
    for d in deployments:
        cloud = cloud_repo.find_by_deployment(d.id)
        incident = err_repo.latest_for_pipeline(d.pipeline_id)
        pipeline_id_str = str(d.pipeline_id) if d.pipeline_id else None

        result.append({
            "id": str(d.id),
            "environment": d.environment,
            "status": d.status,
            "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
            "instance_id": cloud.aws_instance_id if cloud else None,
            "incident": incident.title if incident and d.status == "rolled_back" else None
        })

    return jsonify({"deployments": result})
