import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from backend.repositories import (
    ProjectRepository,
    SimulationRunRepository,
    UserRepository,
)
from backend.models_mongo import UserProfile, SimulationRun as MongoSimulationRun

simulations_bp = Blueprint("simulations", __name__)
logger = logging.getLogger(__name__)


def _get_github_token(user_id) -> str | None:
    """Get GitHub access token from user's embedded profile (MongoDB)."""
    try:
        uid = str(user_id)
    except (TypeError, ValueError):
        return None
    from backend.models_mongo import User as MongoUser
    user = MongoUser.objects(id=uid).first()
    return user.profile.github_access_token if (user and user.profile) else None


@simulations_bp.route("/projects/<project_id>/simulate", methods=["POST"])
@jwt_required()
def start_simulation(project_id):
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    token = _get_github_token(user_id)
    if not token:
        return jsonify({"error": "GitHub not connected"}), 403

    data = request.get_json() or {}
    error_type = data.get("error_type", "syntax_error")
    target_file = data.get("target_file")

    # If no target file provided, try to find one
    if not target_file:
        from backend.services.github_service import GitHubService
        gh = GitHubService(token)
        tree_data = gh.get_repo_tree(project.repo_owner, project.repo_name, project.default_branch or "main")
        if not tree_data or not tree_data.get("tree"):
            return jsonify({"error": "Could not fetch repo tree to find a target file"}), 400

        # Look for standard entrypoints
        candidates = ["app.py", "main.py", "index.js", "src/index.js", "src/App.js", "package.json"]
        tree_paths = [item["path"] for item in tree_data["tree"] if item.get("type") == "blob"]

        for c in candidates:
            if c in tree_paths:
                target_file = c
                break

        if not target_file:
            # Fallback to the first available file
            target_file = tree_paths[0] if tree_paths else "README.md"

    sim_repo = SimulationRunRepository()
    sim = sim_repo.create(
        project_id=str(project.id),
        injected_error_type=error_type,
        injected_file=target_file,
        injected_diff=f"Pending injection for {error_type}",
    )
    # Set status to running
    sim_repo.update_result(str(sim.id), status="running")

    from backend.services.simulation_service import run_simulation
    run_simulation.delay(str(sim.id), token)

    return jsonify({"message": "Simulation started", "simulation": sim.to_dict()}), 201


@simulations_bp.route("/projects/<project_id>/simulations", methods=["GET"])
@jwt_required()
def list_simulations(project_id):
    user_id = get_jwt_identity()
    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(project_id, user_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    sim_repo = SimulationRunRepository()
    sims = sim_repo.find_by_project(str(project.id))
    return jsonify({"simulations": [s.to_dict() for s in sims]})


@simulations_bp.route("/simulations/<sim_id>", methods=["GET"])
@jwt_required()
def get_simulation(sim_id):
    user_id = get_jwt_identity()
    sim_repo = SimulationRunRepository()
    sim = sim_repo.get_by_id(sim_id)
    if not sim:
        return jsonify({"error": "Simulation not found"}), 404

    project_repo = ProjectRepository()
    project = project_repo.find_by_id_for_user(str(sim.project_id), user_id)
    if not project:
        return jsonify({"error": "Simulation not found"}), 404

    return jsonify({"simulation": sim.to_dict()})
