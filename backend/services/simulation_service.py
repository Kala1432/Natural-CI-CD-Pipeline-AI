import time
import logging
from backend.celery_app import celery_app
from backend.repositories import SimulationRunRepository, ProjectRepository
from flask import current_app, has_app_context

def _get_app():
    if has_app_context():
        return current_app._get_current_object()
    from backend.app import create_app
    return create_app()

logger = logging.getLogger(__name__)


def _set_sim_status(sim_id: str, status: str, log: str = None, diag: str = None, diff: str = None):
    app = _get_app()
    with app.app_context():
        sim_repo = SimulationRunRepository()
        kwargs = {"status": status}
        if log is not None:
            kwargs["pipeline_log"] = log
        if diag is not None:
            kwargs["ai_diagnosis"] = diag
        if diff is not None:
            kwargs["ai_fix_diff"] = diff
        sim_repo.update_result(sim_id, **kwargs)


@celery_app.task
def run_simulation(sim_id: str, token: str):
    """Run the chaos engineering simulation."""
    app = _get_app()
    with app.app_context():
        sim_repo = SimulationRunRepository()
        sim = sim_repo.get_by_id(sim_id)
        if not sim:
            return

        project_repo = ProjectRepository()
        project = project_repo.get_by_id(str(sim.project_id))
        if not project:
            return
        owner = project.repo_owner
        repo = project.repo_name
        base_branch = project.default_branch or "main"

        sim_branch = f"pipeline-sh-simulation-{sim_id}"

    from backend.services.github_service import GitHubService
    from backend.services.ai_service import AIService
    gh = GitHubService(token)
    ai = AIService()

    try:
        # Step 1: Create simulation branch
        logger.info("[sim-%s] Creating branch %s from %s", sim_id, sim_branch, base_branch)
        branch_resp = gh.create_branch(owner, repo, sim_branch, base_branch)
        if "error" in branch_resp and not branch_resp.get("already_exists"):
            _set_sim_status(sim_id, "error", log=f"Failed to create branch: {branch_resp['error']}")
            return

        # Step 2: Fetch target file
        logger.info("[sim-%s] Fetching file %s", sim_id, sim.injected_file)
        original_content = gh.get_file_content(owner, repo, sim.injected_file, base_branch)
        if not original_content:
            _set_sim_status(sim_id, "error", log=f"Failed to fetch {sim.injected_file}")
            return

        # Inject error
        broken_content = original_content
        if sim.injected_error_type == "syntax_error":
            broken_content += "\n\n) SYNTAX ERROR INJECTED"
        elif sim.injected_error_type == "missing_import":
            lines = broken_content.splitlines()
            # Remove the first import statement
            broken_content = "\n".join([line for line in lines if not line.startswith("import ") and not line.startswith("from ")])
        elif sim.injected_error_type == "failing_test":
            broken_content += "\n\ndef test_simulation_failure():\n    assert False, 'Injected Failure'\n"

        if broken_content == original_content:
            broken_content += "\n\n# INJECTED SYNTAX ERROR\ninvalid_python_code() {"

        # Step 3: Commit broken file
        logger.info("[sim-%s] Committing broken file", sim_id)
        commit_resp = gh.commit_file(
            repo_full_name=f"{owner}/{repo}",
            branch=sim_branch,
            file_path=sim.injected_file,
            commit_message=f"Inject {sim.injected_error_type}",
            file_content=broken_content
        )
        if not commit_resp or "error" in commit_resp:
            _set_sim_status(sim_id, "error", log="Failed to commit broken file")
            return

        # Step 4: Poll GitHub Actions for failure
        logger.info("[sim-%s] Waiting for CI to fail...", sim_id)
        failed_run_id = None
        for _ in range(15): # wait up to 150 seconds
            time.sleep(10)
            runs = gh.get_workflow_runs(owner, repo, sim_branch)
            if runs and runs.get("workflow_runs"):
                latest_run = runs["workflow_runs"][0]
                status = latest_run.get("status")
                conclusion = latest_run.get("conclusion")
                logger.info("[sim-%s] CI status: %s, conclusion: %s", sim_id, status, conclusion)
                if status == "completed":
                    if conclusion == "failure":
                        failed_run_id = latest_run.get("id")
                        break
                    else:
                        _set_sim_status(sim_id, "error", log="CI completed but did not fail as expected.")
                        return

        if not failed_run_id:
            _set_sim_status(sim_id, "error", log="Timed out waiting for CI to fail.")
            return

        _set_sim_status(sim_id, "failed_as_expected")

        # Step 5: Fetch Logs
        logger.info("[sim-%s] Fetching CI logs for run %s", sim_id, failed_run_id)
        ci_logs = gh.get_workflow_run_logs(owner, repo, failed_run_id)
        if not ci_logs:
            _set_sim_status(sim_id, "error", log="Could not fetch CI logs.")
            return

        _set_sim_status(sim_id, "failed_as_expected", log=ci_logs[-10000:])

        # Step 6: Diagnose & Fix with AI
        logger.info("[sim-%s] Analyzing logs and generating fix", sim_id)
        diagnosis = ai.analyze_logs(ci_logs)
        fixed_content = ai.generate_code_fix(broken_content, ci_logs)

        if not fixed_content:
            _set_sim_status(sim_id, "error", diag=diagnosis.get("debug_advice"), log="AI failed to generate a fix.")
            return

        # Note: Ideally we compute a diff, but for simplicity we store the new content
        # or a placeholder diff.
        ai_diff = "--- " + sim.injected_file + "\n+++ " + sim.injected_file + "\n+ Fixed by AI"
        _set_sim_status(sim_id, "running", diag=diagnosis.get("debug_advice"), diff=ai_diff)

        # Step 7: Commit fix
        logger.info("[sim-%s] Committing fixed file", sim_id)
        fix_commit = gh.commit_file(
            repo_full_name=f"{owner}/{repo}",
            branch=sim_branch,
            file_path=sim.injected_file,
            commit_message="Auto-fix by Pipeline.sh AI",
            file_content=fixed_content
        )
        if not fix_commit or "error" in fix_commit:
            _set_sim_status(sim_id, "error", log="Failed to commit AI fix.")
            return

        # Step 8: Poll for success
        logger.info("[sim-%s] Waiting for CI to pass...", sim_id)
        for _ in range(15):
            time.sleep(10)
            runs = gh.get_workflow_runs(owner, repo, sim_branch)
            if runs and runs.get("workflow_runs"):
                latest_run = runs["workflow_runs"][0]
                status = latest_run.get("status")
                conclusion = latest_run.get("conclusion")
                if status == "completed":
                    if conclusion == "success":
                        _set_sim_status(sim_id, "ai_fixed")
                        logger.info("[sim-%s] Simulation successfully AI Fixed!", sim_id)
                        return
                    else:
                        _set_sim_status(sim_id, "error", log="CI failed again after AI fix.")
                        return

        _set_sim_status(sim_id, "error", log="Timed out waiting for CI to pass after fix.")

    except Exception as exc:
        logger.exception("[sim-%s] Simulation failed unexpectedly", sim_id)
        _set_sim_status(sim_id, "error", log=str(exc))
