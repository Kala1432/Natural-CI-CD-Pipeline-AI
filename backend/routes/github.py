from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.services.github_service import GitHubService
from backend.repositories import (
    UserRepository,
    RepositoryRepository,
    ProjectRepository,
)
from backend.models_mongo import User, UserProfile


github_bp = Blueprint("github", __name__)


def _get_user_dict(user_id):
    """Get user dict from MongoDB by ID string."""
    user_repo = UserRepository()
    return user_repo.get_by_id_str(user_id)


@github_bp.route("/repos", methods=["GET"])
@jwt_required()
def list_repositories():
    user_id = get_jwt_identity()
    user = _get_user_dict(user_id)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    token = request.headers.get("X-GitHub-Token")
    profile = user.get("profile") or {}
    if not token and profile.get("github_connected"):
        token = profile.get("github_access_token")

    if not token:
        return jsonify({"error": "GitHub token not provided and GitHub account not connected"}), 400

    github = GitHubService(token)
    repos = github.list_user_repositories()
    result = []
    for item in repos:
        result.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "full_name": item.get("full_name"),
            "private": item.get("private"),
            "default_branch": item.get("default_branch"),
        })
    return jsonify({"repositories": result})


@github_bp.route("/connect", methods=["POST"])
@jwt_required()
def connect_repository():
    data = request.get_json() or {}
    user_id = get_jwt_identity()
    user = _get_user_dict(user_id)

    token = request.headers.get("X-GitHub-Token")
    profile = user.get("profile") if user else {}
    if not token and profile and profile.get("github_connected"):
        token = profile.get("github_access_token")

    repo_full_name = data.get("full_name")
    if not repo_full_name:
        return jsonify({"error": "Repository full_name is required"}), 400
    if not token:
        return jsonify({"error": "GitHub not connected"}), 403

    github = GitHubService(token)
    repo_data = github.get_repository(repo_full_name)
    if not repo_data:
        return jsonify({"error": "Repository not found"}), 404

    repo_repo = RepositoryRepository()
    local_repo = repo_repo.find_by_github_id(str(repo_data.get("id")))
    if not local_repo:
        local_repo = repo_repo.create(
            user_id=user_id,
            github_repo_id=str(repo_data.get("id")),
            name=repo_data.get("name"),
            full_name=repo_data.get("full_name"),
            visibility="private" if repo_data.get("private") else "public",
            default_branch=repo_data.get("default_branch", "main"),
        )
    return jsonify({"repository": {
        "id": str(local_repo.id),
        "name": local_repo.name,
        "full_name": local_repo.full_name,
        "visibility": local_repo.visibility,
        "default_branch": local_repo.default_branch,
    }})


@github_bp.route("/generate-workflow", methods=["POST"])
@jwt_required()
def generate_workflow():
    data = request.get_json() or {}
    project_type = data.get("project_type", "python")
    branch = data.get("branch", "main")
    workflow_name = data.get("workflow_name", "pipeline-sh-ci")

    template = GitHubService.generate_workflow_template(project_type, workflow_name, branch)
    return jsonify({"workflow": template})


@github_bp.route("/webhook", methods=["POST"])
def github_webhook():
    payload = request.get_json() or {}
    event = request.headers.get("X-GitHub-Event", "push")

    if event == "push":
        repo_data = payload.get("repository") or {}
        full_name = repo_data.get("full_name")  # owner/repo
        if full_name and "/" in full_name:
            owner, repo_name = full_name.split("/", 1)
            project_repo = ProjectRepository()
            projects = project_repo.find_by_repo(owner, repo_name)
            for p in projects:
                # UserProfile is embedded in User, so fetch the user (not a separate collection)
                from backend.models_mongo import User as MongoUser
                owner = MongoUser.objects(id=p.created_by).first()
                token = owner.profile.github_access_token if (owner and owner.profile) else None
                if token:
                    from backend.services.analyze_service import analyze_repo
                    import threading
                    threading.Thread(target=analyze_repo, args=(str(p.id), token), daemon=True).start()
                    current_app.logger.info("Webhook triggered re-analysis for project %s (%s)", p.id, full_name)

    return jsonify({"event": event, "received": True}), 200
