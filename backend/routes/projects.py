import logging
import threading

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.db import db
from backend.models import AutomationStep, GeneratedWorkflow, Project, User, UserProfile

projects_bp = Blueprint("projects", __name__)
logger = logging.getLogger(__name__)


def _get_github_token(user_id) -> str | None:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    profile = UserProfile.query.filter_by(user_id=uid).first()
    return profile.github_access_token if profile else None


def _parse_repo_url(url: str):
    """Extract owner and repo name from a GitHub URL."""
    url = url.strip().rstrip("/")
    # Handle https://github.com/owner/repo and git@github.com:owner/repo
    if "github.com" not in url:
        return None, None
    if url.startswith("git@"):
        path = url.split("github.com:")[-1]
    else:
        path = url.split("github.com/")[-1]
    path = path.replace(".git", "")
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


@projects_bp.route("", methods=["POST"])
@jwt_required()
def create_project():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    repo_url = (data.get("repo_url") or "").strip()

    if not repo_url:
        return jsonify({"error": "repo_url is required"}), 400

    if "github.com" not in repo_url:
        return jsonify({"error": "Only GitHub repositories are supported"}), 400

    owner, repo_name = _parse_repo_url(repo_url)
    if not owner or not repo_name:
        return jsonify({"error": "Could not parse owner/repo from URL. Use format: https://github.com/owner/repo"}), 400

    token = _get_github_token(user_id)
    if not token:
        return jsonify({"error": "GitHub not connected. Connect GitHub in Settings first."}), 403

    from backend.services.github_service import GitHubService
    gh = GitHubService(token)
    repo_data = gh.get_repository(f"{owner}/{repo_name}")

    if not repo_data or repo_data.get("message") == "Not Found" or "id" not in repo_data:
        return jsonify({"error": "Repo not found or you don't have access"}), 404

    existing = Project.query.filter_by(
        created_by=user_id,
        repo_owner=owner,
        repo_name=repo_name,
    ).first()
    if existing:
        return jsonify({"error": "You already have a project for this repository", "project_id": existing.id}), 409

    project = Project(
        created_by=user_id,
        repo_url=repo_url,
        repo_owner=owner,
        repo_name=repo_name,
        default_branch=repo_data.get("default_branch", "main"),
        status="pending_analysis",
    )
    db.session.add(project)
    db.session.commit()

    # Kick off analysis in background thread immediately
    from backend.services.analyze_service import analyze_repo
    from flask import current_app
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=analyze_repo,
        args=(app, project.id, token),
        daemon=True,
    )
    thread.start()

    logger.info("Created project %s for %s/%s, analysis started", project.id, owner, repo_name)
    return jsonify({"project": project.to_dict()}), 201


@projects_bp.route("", methods=["GET"])
@jwt_required()
def list_projects():
    user_id = int(get_jwt_identity())
    projects = (
        Project.query
        .filter_by(created_by=user_id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return jsonify({"projects": [p.to_dict() for p in projects]})


@projects_bp.route("/<int:project_id>", methods=["GET"])
@jwt_required()
def get_project(project_id):
    user_id = int(get_jwt_identity())
    project = Project.query.filter_by(id=project_id, created_by=user_id).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404

    steps = AutomationStep.query.filter_by(project_id=project_id).order_by(AutomationStep.id).all()
    workflow = GeneratedWorkflow.query.filter_by(project_id=project_id).order_by(GeneratedWorkflow.id.desc()).first()

    return jsonify({
        "project": project.to_dict(),
        "steps": [s.to_dict() for s in steps],
        "workflow": workflow.to_dict() if workflow else None,
    })


@projects_bp.route("/<int:project_id>", methods=["DELETE"])
@jwt_required()
def delete_project(project_id):
    user_id = int(get_jwt_identity())
    project = Project.query.filter_by(id=project_id, created_by=user_id).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404
    db.session.delete(project)
    db.session.commit()
    return jsonify({"message": "Project deleted"})


@projects_bp.route("/<int:project_id>/status", methods=["GET"])
@jwt_required()
def get_project_status(project_id):
    """Lightweight polling endpoint — returns only status + error_message."""
    user_id = int(get_jwt_identity())
    project = Project.query.filter_by(id=project_id, created_by=user_id).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({"status": project.status, "error_message": project.error_message})


@projects_bp.route("/<int:project_id>/analyze", methods=["POST"])
@jwt_required()
def reanalyze_project(project_id):
    """Trigger a fresh analysis for an existing project."""
    user_id = int(get_jwt_identity())
    project = Project.query.filter_by(id=project_id, created_by=user_id).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if project.status in ("pending_analysis", "analyzed"):
        return jsonify({"error": "Analysis already in progress"}), 409

    token = _get_github_token(user_id)
    if not token:
        return jsonify({"error": "GitHub not connected"}), 403

    project.status = "pending_analysis"
    project.error_message = None
    db.session.commit()

    from backend.services.analyze_service import analyze_repo
    from flask import current_app
    app = current_app._get_current_object()
    threading.Thread(target=analyze_repo, args=(app, project.id, token), daemon=True).start()

    logger.info("Re-analysis triggered for project %s", project_id)
    return jsonify({"message": "Analysis started", "project": project.to_dict()})


@projects_bp.route("/<int:project_id>/steps", methods=["PATCH"])
@jwt_required()
def update_steps(project_id):
    """Bulk approve/reject steps. Body: [{id, approved}, ...]"""
    user_id = int(get_jwt_identity())
    project = Project.query.filter_by(id=project_id, created_by=user_id).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if project.status not in ("awaiting_approval", "pr_created"):
        return jsonify({"error": "Project is not awaiting approval"}), 409

    updates = request.get_json() or []
    if not isinstance(updates, list):
        return jsonify({"error": "Expected a list of {id, approved}"}), 400

    ids = [u["id"] for u in updates if "id" in u]
    steps = AutomationStep.query.filter(
        AutomationStep.project_id == project_id,
        AutomationStep.id.in_(ids),
    ).all()
    step_map = {s.id: s for s in steps}

    for u in updates:
        step = step_map.get(u.get("id"))
        if step and "approved" in u:
            step.approved = bool(u["approved"])

    db.session.commit()
    all_steps = AutomationStep.query.filter_by(project_id=project_id).order_by(AutomationStep.id).all()
    return jsonify({"steps": [s.to_dict() for s in all_steps]})


@projects_bp.route("/<int:project_id>/generate", methods=["POST"])
@jwt_required()
def generate_workflow(project_id):
    """Generate YAML from approved steps and save as GeneratedWorkflow."""
    user_id = int(get_jwt_identity())
    project = Project.query.filter_by(id=project_id, created_by=user_id).first()
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if project.status not in ("awaiting_approval", "pr_created"):
        return jsonify({"error": "Project is not awaiting approval"}), 409

    approved = AutomationStep.query.filter_by(
        project_id=project_id, approved=True
    ).order_by(AutomationStep.id).all()

    if not approved:
        return jsonify({"error": "No steps approved. Approve at least one step first."}), 400

    project.status = "generating_yaml"
    db.session.commit()

    try:
        from backend.services.workflow_service import build_workflow
        yaml_content = build_workflow(project, approved)
    except Exception as exc:
        logger.exception("Workflow generation failed for project %s", project_id)
        project.status = "awaiting_approval"
        db.session.commit()
        return jsonify({"error": f"YAML generation failed: {exc}"}), 500

    # Delete any previous draft workflow
    GeneratedWorkflow.query.filter_by(project_id=project_id, pr_status="draft").delete()

    workflow = GeneratedWorkflow(
        project_id=project_id,
        filename=".github/workflows/hifi-ci.yml",
        yaml_content=yaml_content,
        pr_status="draft",
    )
    db.session.add(workflow)
    project.status = "awaiting_approval"
    db.session.commit()

    logger.info("Workflow generated for project %s (%d bytes)", project_id, len(yaml_content))
    return jsonify({"workflow": workflow.to_dict()}), 201
