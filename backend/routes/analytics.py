from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from backend.models_mongo import (
    AuditLog,
    Deployment,
    Project,
    SimulationRun,
)
from backend.repositories import (
    AuditLogRepository,
    DeploymentRepository,
    ProjectRepository,
)
from backend.services.tf_predictor import TFPredictor

analytics_bp = Blueprint("analytics", __name__)


def _compute_failure_risk_score() -> int:
    """Compute a 0–100 failure risk score from login audit logs in the last 7 days."""
    since = datetime.utcnow() - timedelta(days=7)
    logs = list(
        AuditLog.objects(
            action__in=["user.login.failed", "user.login.success"],
            created_at__gte=since,
        )
    )
    if not logs:
        return 0

    failed = sum(1 for log in logs if log.action == "user.login.failed")
    total = len(logs)
    # High ratio of failures → higher risk score
    failure_ratio = failed / total
    return int(min(100, round(failure_ratio * 100)))


def _compute_deployment_health() -> str:
    """Compute deployment health: green ≥70%, yellow ≥40%, else red."""
    deployments = list(Deployment.objects())
    if not deployments:
        return "green"
    completed = [d for d in deployments if d.status in ("completed", "success")]
    if not completed:
        return "green"
    success_rate = len([d for d in completed if d.status == "success"]) / len(completed)
    if success_rate >= 0.7:
        return "green"
    elif success_rate >= 0.4:
        return "yellow"
    return "red"


def _generate_recommendations(projects: list[Project]) -> list[str]:
    """Generate recommendations based on aggregate gaps across analyzed projects."""
    if not projects:
        return [
            "Add your first project to start receiving pipeline recommendations.",
        ]

    needs_tests = sum(1 for p in projects if not (p.detected_stack and p.detected_stack.has_tests))
    needs_docker = sum(1 for p in projects if not (p.detected_stack and p.detected_stack.has_dockerfile))
    needs_ci = sum(1 for p in projects if not (p.detected_stack and p.detected_stack.has_ci))

    recommendations = []
    if needs_tests:
        recommendations.append(f"Enable tests in {needs_tests} project(s) — automated tests reduce regressions by ~40%.")
    if needs_docker:
        recommendations.append(f"Add Docker configuration to {needs_docker} project(s) for consistent deployments.")
    if needs_ci:
        recommendations.append(f"Set up CI pipelines for {needs_ci} project(s) to automate builds on every push.")
    if len(projects) >= 3:
        avg_score = sum(p.readiness_score or 0 for p in projects) / len(projects)
        if avg_score < 50:
            recommendations.append(
                f"Average readiness score is {avg_score:.0f}/100 — prioritize CI, tests, and Docker to improve."
            )
    if not recommendations:
        recommendations.append("All projects have strong foundations. Consider adding deployment automation next.")
    return recommendations[:4]


def _build_pipeline_history() -> list[dict]:
    """
    Build a 14-day pipeline history from AuditLog records.
    Groups by day and counts events by status.
    Falls back to synthetic data from Project readiness scores if no audit log data exists.
    """
    since = datetime.utcnow() - timedelta(days=14)

    # Try to use audit log deployment events
    logs = list(
        AuditLog.objects(
            action__in=["deployment.triggered", "deployment.completed", "deployment.failed"],
            created_at__gte=since,
        ).order_by("created_at")
    )

    if logs:
        # Group by day
        daily = defaultdict(lambda: {"success": 0, "failure": 0})
        for log in logs:
            day = log.created_at.strftime("%Y-%m-%d")
            if log.action == "deployment.failed" or log.status == "failure":
                daily[day]["failure"] += 1
            else:
                daily[day]["success"] += 1

        today = datetime.utcnow()
        result = []
        for i in range(14):
            day = (today - timedelta(days=13 - i)).strftime("%Y-%m-%d")
            result.append({
                "date": day,
                "name": (today - timedelta(days=13 - i)).strftime("%a"),
                "success": daily[day]["success"],
                "failure": daily[day]["failure"],
            })
        return result

    # Fallback: generate synthetic history from current project readiness scores
    projects = list(Project.objects(readiness_score__ne=None))
    if projects:
        avg_score = sum(p.readiness_score for p in projects) / len(projects) / 100.0
        success_rate = max(avg_score, 0.5)
        today = datetime.utcnow()
        return [
            {
                "date": (today - timedelta(days=13 - i)).strftime("%Y-%m-%d"),
                "name": (today - timedelta(days=13 - i)).strftime("%a"),
                "success": int(success_rate * (80 + i * 2)),
                "failure": int((1 - success_rate) * (20 + i)),
            }
            for i in range(14)
        ]

    # No data: return empty list — frontend handles empty state gracefully
    return []


@analytics_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def dashboard_metrics():
    project_repo = ProjectRepository()
    deploy_repo = DeploymentRepository()
    audit_repo = AuditLogRepository()

    # Active repos: projects that have been analyzed (not still pending)
    analyzed_statuses = ["analyzed", "awaiting_approval", "workflow_generated"]
    active_repos = Project.objects(status__in=analyzed_statuses).count()

    # All projects for readiness-based metrics
    all_projects = list(Project.objects())
    total_projects = len(all_projects)

    # Success rate: weighted average of readiness scores
    scored = [p for p in all_projects if p.readiness_score is not None]
    if scored:
        success_rate = round(sum(p.readiness_score for p in scored) / len(scored), 1)
    else:
        success_rate = 0.0

    # Deployment health
    deployment_health = _compute_deployment_health()

    # Failure risk from login audit logs
    failure_risk_score = _compute_failure_risk_score()

    # Recommendations
    recommendations = _generate_recommendations(all_projects)

    # Pipeline history
    pipeline_history = _build_pipeline_history()

    # Failure risk score via ML predictor (enriches the audit-log-based score)
    predictor = TFPredictor()
    ml_prediction = predictor.predict_failure_risk({
        "recent_failures": failure_risk_score // 10,
        "success_rate": success_rate / 100.0,
    })
    # Blend: 40% ML predictor + 60% audit-log derived score
    ml_risk = ml_prediction.get("failure_risk", 0)
    failure_risk_score = round(0.4 * ml_risk + 0.6 * failure_risk_score, 1)

    return jsonify({
        "active_repos": active_repos,
        "total_projects": total_projects,
        "success_rate": success_rate,
        "deployment_health": deployment_health,
        "failure_risk_score": failure_risk_score,
        "recommendations": recommendations,
        "pipeline_history": pipeline_history,
    })
