import logging
import threading

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.repositories import (
    ProjectRepository,
    AutomationStepRepository,
    GeneratedWorkflowRepository,
    UserRepository,
)
from backend.models_mongo import User, UserProfile

projects_bp = Blueprint("projects", __name__)
logger = logging.getLogger(__name__)


def _get_github_token(user_id) -> str | None:
    """Get GitHub access token from a user's MongoDB profile document."""
    try:
        uid = str(user_id)
    except (TypeError, ValueError):
        return None
    from backend.models_mongo import User as MongoUser
    user = MongoUser.objects(id=uid).first()
    if not user or not user.profile:
        return None
    return user.profile.github_access_token or None


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
    user_id = get_jwt_identity()
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

    project_repo = ProjectRepository()
    # Check by full path
    all_user_projects = project_repo.find_by_creator(user_id)
    existing = next(
        (p for p in all_user_projects
         if p.repo_owner == owner and p.repo_name == repo_name),
        None,
    )
    if existing:
        return jsonify({
            "error": "You already have a project for this repository",
            "project_id": str(existing.id),
        }), 409

    project = project_repo.create(
        created_by=user_id,
        repo_url=repo_url,
        repo_owner=owner,
        repo_name=repo_name,
        default_branch=repo_data.get("default_branch", "main"),
    )

    # Kick off analysis in background via Celery
    from backend.services.analyze_service import analyze_repo
    analyze_repo.delay(str(project.id), token)

    logger.info("Created project %s for %s/%s, analysis started", project.id, owner, repo_name)
    return jsonify({"project": project.to_dict()}), 201


@projects_bp.route("", methods=["GET"])
@jwt_required()
def list_projects():
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    projects = project_repo.find_by_creator(user_id)
    return jsonify({"projects": [p.to_dict() for p in projects]})


@projects_bp.route("/<project_id>", methods=["GET"])
@jwt_required()
def get_project(project_id):
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    step_repo = AutomationStepRepository()
    wf_repo = GeneratedWorkflowRepository()

    steps = step_repo.find_by_project(project_id)
    workflow = wf_repo.latest_for_project(project_id)

    return jsonify({
        "project": project.to_dict(),
        "steps": [s.to_dict() for s in steps],
        "workflow": workflow.to_dict() if workflow else None,
    })


@projects_bp.route("/<project_id>", methods=["DELETE"])
@jwt_required()
def delete_project(project_id):
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    project_repo.delete_by_id(project_id)
    return jsonify({"message": "Project deleted"})


@projects_bp.route("/<project_id>/status", methods=["GET"])
@jwt_required()
def get_project_status(project_id):
    """Lightweight polling endpoint — returns only status + error_message."""
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({"status": project.status, "error_message": project.error_message})


@projects_bp.route("/<project_id>/analyze", methods=["POST"])
@jwt_required()
def reanalyze_project(project_id):
    """Trigger a fresh analysis for an existing project."""
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if project.status == "pending_analysis":
        return jsonify({"error": "Analysis already in progress"}), 409

    token = _get_github_token(user_id)
    if not token:
        return jsonify({"error": "GitHub not connected"}), 403

    project_repo.update_status(project_id, "pending_analysis", error_message="")

    from backend.services.analyze_service import analyze_repo
    async_result = analyze_repo.delay(project_id, token)
    task_id = getattr(async_result, "id", None)

    logger.info("Re-analysis triggered for project %s", project_id)
    project = project_repo.get_by_id(project_id)
    return jsonify({"message": "Analysis started", "project": project.to_dict(), "task_id": task_id}), 202


@projects_bp.route("/<project_id>/steps", methods=["PATCH"])
@jwt_required()
def update_steps(project_id):
    """Bulk approve/reject steps. Body: [{id, approved}, ...]"""
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if project.status not in ("awaiting_approval", "pr_created"):
        return jsonify({"error": "Project is not awaiting approval"}), 409

    updates = request.get_json() or []
    if not isinstance(updates, list):
        return jsonify({"error": "Expected a list of {id, approved}"}), 400

    step_repo = AutomationStepRepository()
    from backend.models_mongo import AutomationStep
    for u in updates:
        step_id = u.get("id")
        if not step_id:
            continue
        if "approved" in u:
            AutomationStep.objects(id=step_id, project_id=project_id).update(
                set__approved=bool(u["approved"])
            )

    all_steps = step_repo.find_by_project(project_id)
    return jsonify({"steps": [s.to_dict() for s in all_steps]})


@projects_bp.route("/<project_id>/generate", methods=["POST"])
@jwt_required()
def generate_workflow(project_id):
    """Generate YAML from approved steps and save as GeneratedWorkflow."""
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if project.status not in ("awaiting_approval", "pr_created"):
        return jsonify({"error": "Project is not awaiting approval"}), 409

    step_repo = AutomationStepRepository()
    wf_repo = GeneratedWorkflowRepository()
    all_steps = step_repo.find_by_project(project_id)
    approved = [s for s in all_steps if s.approved]

    if not approved:
        return jsonify({"error": "No steps approved. Approve at least one step first."}), 400

    project_repo.update_status(project_id, "generating_yaml")

    try:
        from backend.services.workflow_service import build_workflow
        yaml_content = build_workflow(project, approved)
    except Exception as exc:
        logger.exception("Workflow generation failed for project %s", project_id)
        project_repo.update_status(project_id, "awaiting_approval")
        return jsonify({"error": f"YAML generation failed: {exc}"}), 500

    # Delete any previous draft workflow
    from backend.models_mongo import GeneratedWorkflow
    GeneratedWorkflow.objects(project_id=project_id, pr_status="draft").delete()

    workflow = wf_repo.create(
        project_id=project_id,
        yaml_content=yaml_content,
        filename=".github/workflows/hifi-ci.yml",
    )
    project_repo.update_status(project_id, "awaiting_approval")

    logger.info("Workflow generated for project %s (%d bytes)", project_id, len(yaml_content))
    return jsonify({"workflow": workflow.to_dict()}), 201


@projects_bp.route("/<project_id>/publish", methods=["POST"])
@jwt_required()
def publish_workflow(project_id):
    """Publish generated workflow YAML. Method can be 'commit' or 'pr'."""
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    wf_repo = GeneratedWorkflowRepository()
    workflow = wf_repo.latest_for_project(project_id)
    if not workflow:
        return jsonify({"error": "No generated workflow found. Generate one first."}), 400

    data = request.get_json() or {}
    method = data.get("method", "pr")
    commit_message = data.get("commit_message") or "Add CI/CD workflow via Pipeline.sh"
    branch_name = data.get("branch_name") or "hifi-ci-setup"

    token = _get_github_token(user_id)
    if not token:
        return jsonify({"error": "GitHub not connected"}), 403

    from backend.services.github_service import GitHubService
    gh = GitHubService(token)

    owner = project.repo_owner
    repo = project.repo_name
    default_branch = project.default_branch or "main"

    user_repo = UserRepository()
    user_dict = user_repo.get_by_id_str(user_id)
    if user_dict:
        author_name = user_dict.get("name") or (
            user_dict.get("email", "").split("@")[0] if user_dict.get("email") else "Pipeline.sh"
        )
        author_email = user_dict.get("email") or "pipeline@example.com"
    else:
        author_name = "Pipeline.sh"
        author_email = "pipeline@example.com"

    if method == "commit":
        resp = gh.commit_workflow_file(
            repo_full_name=f"{owner}/{repo}",
            branch=default_branch,
            file_path=workflow.filename,
            commit_message=commit_message,
            yaml_content=workflow.yaml_content,
            author_name=author_name,
            author_email=author_email
        )
        if not resp or "error" in resp:
            err_msg = resp.get("error", "GitHub commit failed") if resp else "Empty response"
            err_str = str(err_msg).lower()
            if ("push access" in err_str or "permission" in err_str
                    or "resource not accessible" in err_str or "403" in err_str):
                return jsonify({"error": "You do not have direct write permissions to commit to this repository. Please choose the 'Pull Request' option instead."}), 403

            logger.error("GitHub direct commit failed for project %s: %s", project_id, err_msg)
            return jsonify({"error": f"GitHub commit failed: {err_msg}"}), 400

        wf_repo.update_pr(workflow.id, pr_url=resp.get("html_url", ""), pr_number=0, pr_status="merged")
        project_repo.update_status(project_id, "pr_merged")
        workflow.reload()  # refresh to get updated fields

        logger.info("Directly committed workflow for project %s to %s/%s@%s", project_id, owner, repo, default_branch)
        return jsonify({"success": True, "message": "Workflow committed directly to default branch", "workflow": workflow.to_dict()}), 200

    elif method == "pr":
        head_ref = branch_name
        target_repo_owner = owner

        existing_pr = gh.get_existing_pull_request(owner, repo, branch_name)
        if existing_pr:
            wf_repo.update_pr(workflow.id, pr_url=existing_pr.get("html_url", ""), pr_number=existing_pr.get("number", 0), pr_status="open")
            project_repo.update_status(project_id, "pr_created")
            workflow.reload()
            return jsonify({
                "success": True,
                "message": "A Pull Request is already open on GitHub for this workflow.",
                "workflow": workflow.to_dict(),
            }), 200

        branch_resp = gh.create_branch(owner, repo, branch_name, default_branch)

        if "error" in branch_resp and not branch_resp.get("already_exists"):
            err_text = str(branch_resp.get("error", ""))
            is_perm_issue = (
                branch_resp.get("status_code") in (403, 404) or
                "push access" in err_text.lower() or
                "resource not accessible" in err_text.lower() or
                "permission" in err_text.lower()
            )
            if is_perm_issue:
                logger.info("Direct branch creation on %s/%s restricted; attempting Fork workflow", owner, repo)
                gh_user = gh.get_authenticated_user()
                if not gh_user or not gh_user.get("login"):
                    return jsonify({"error": "Could not fetch your GitHub user details to fork the repository."}), 403

                fork_owner = gh_user["login"]
                fork_resp = gh.fork_repository(owner, repo)
                if "error" in fork_resp:
                    return jsonify({"error": f"Could not fork repository: {fork_resp['error']}"}), 400

                target_repo_owner = fork_owner
                head_ref = f"{fork_owner}:{branch_name}"

                existing_fork_pr = gh.get_existing_pull_request(owner, repo, head_ref)
                if existing_fork_pr:
                    wf_repo.update_pr(workflow.id, pr_url=existing_fork_pr.get("html_url", ""), pr_number=existing_fork_pr.get("number", 0), pr_status="open")
                    project_repo.update_status(project_id, "pr_created")
                    workflow.reload()
                    return jsonify({
                        "success": True,
                        "message": "A Pull Request from your fork is already open on GitHub.",
                        "workflow": workflow.to_dict(),
                    }), 200

                branch_resp = gh.create_branch(fork_owner, repo, branch_name, default_branch)
                if "error" in branch_resp and not branch_resp.get("already_exists"):
                    return jsonify({"error": f"Failed to create branch on your fork: {branch_resp['error']}"}), 400
            else:
                return jsonify({"error": f"Failed to create branch: {branch_resp['error']}"}), 400

        commit_resp = gh.commit_workflow_file(
            repo_full_name=f"{target_repo_owner}/{repo}",
            branch=branch_name,
            file_path=workflow.filename,
            commit_message=commit_message,
            yaml_content=workflow.yaml_content,
            author_name=author_name,
            author_email=author_email
        )
        if not commit_resp or "error" in commit_resp:
            err_msg = commit_resp.get("error", "GitHub commit returned an empty response") if commit_resp else "Empty response"
            logger.error("GitHub PR branch commit failed for project %s: %s", project_id, err_msg)
            return jsonify({"error": f"GitHub commit failed: {err_msg}"}), 400

        pr_title = commit_message
        pr_body = (
            "This Pull Request adds an automated CI/CD workflow generated by Pipeline.sh "
            "based on your approved automation steps."
        )
        pr_resp = gh.create_pull_request(owner, repo, pr_title, head_ref, default_branch, pr_body)
        if "error" in pr_resp:
            err_msg = str(pr_resp.get("error"))
            existing_pr = None
            if pr_resp.get("status_code") == 422 and "pull request already exists" in err_msg.lower():
                logger.info("GitHub create PR reported an existing PR for %s/%s head=%s", owner, repo, head_ref)
                existing_pr = gh.get_existing_pull_request(owner, repo, head_ref)
                if not existing_pr and ":" in head_ref:
                    existing_pr = gh.get_existing_pull_request(owner, repo, head_ref.split(":", 1)[1])
                if not existing_pr:
                    existing_pr = gh.get_existing_pull_request(owner, repo, branch_name)
            if not existing_pr:
                existing_pr = gh.get_existing_pull_request(owner, repo, head_ref) or gh.get_existing_pull_request(owner, repo, branch_name)
            if existing_pr:
                wf_repo.update_pr(workflow.id, pr_url=existing_pr.get("html_url", ""), pr_number=existing_pr.get("number", 0), pr_status="open")
                project_repo.update_status(project_id, "pr_created")
                workflow.reload()
                return jsonify({"success": True, "message": "Pull request is open on GitHub", "workflow": workflow.to_dict()}), 200
            return jsonify({"error": f"Failed to open Pull Request: {err_msg}"}), 400

        wf_repo.update_pr(workflow.id, pr_url=pr_resp.get("html_url", ""), pr_number=pr_resp.get("number", 0), pr_status="open")
        project_repo.update_status(project_id, "pr_created")
        workflow.reload()

        logger.info("Created PR for project %s: %s", project_id, pr_resp.get("html_url", ""))
        return jsonify({"success": True, "message": "Pull request created successfully", "workflow": workflow.to_dict()}), 201

    else:
        return jsonify({"error": "Invalid publish method. Expected 'commit' or 'pr'."}), 400

