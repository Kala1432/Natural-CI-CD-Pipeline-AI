from flask import Blueprint, jsonify, request
from backend.repositories import (
    UserRepository,
    ProjectRepository,
    DeploymentRepository,
    ErrorReportRepository,
    AuditLogRepository,
)
from backend.utils.auth import admin_required, get_current_authenticated_user

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/stats", methods=["GET"])
@admin_required()
def admin_stats():
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    deploy_repo = DeploymentRepository()
    err_repo = ErrorReportRepository()

    total_users = user_repo.count()
    total_projects = project_repo.count()
    total_deployments = deploy_repo.count()
    active_deployments = deploy_repo.count_active()
    total_errors = err_repo.count()

    # Simple error rate calc
    error_rate = 0
    if total_deployments > 0:
        error_rate = round((total_errors / total_deployments) * 100, 1)

    return jsonify({
        "total_users": total_users,
        "total_projects": total_projects,
        "total_deployments": total_deployments,
        "active_deployments": active_deployments,
        "total_errors": total_errors,
        "platform_error_rate": error_rate
    }), 200


@admin_bp.route("/audit-logs", methods=["GET"])
@admin_required()
def get_audit_logs():
    limit = min(int(request.args.get("limit", 50)), 200)
    action = request.args.get("action")
    status = request.args.get("status")

    repo = AuditLogRepository()
    logs = repo.list_recent(limit=limit, action=action, status=status)
    return jsonify({
        "audit_logs": [log.to_dict() for log in logs],
        "count": len(logs),
    }), 200

