import json
import logging
from typing import Dict, List, Optional

import yaml

from backend.db import db
from backend.models import Repository, User
from backend.services.cache_service import CacheService
from backend.services.github_service import GitHubService

logger = logging.getLogger(__name__)


class WorkflowEngineError(Exception):
    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


def detect_tech_stack(repo: dict) -> Dict[str, bool]:
    """Return lightweight tech stack flags for a repository payload."""
    allowed_keys = ["python", "flask", "django", "fastapi", "node", "react", "vite", "docker"]

    name = str(repo.get("name", "")).lower()
    description = str(repo.get("description", "")).lower()
    language = str(repo.get("language", "")).lower()
    topics = [str(topic).lower() for topic in repo.get("topics", [])]

    combined = f"{name} {description} {' '.join(topics)}"

    detected = {
        "python": language == "python" or any(k in combined for k in ["python", "flask", "django", "fastapi"]),
        "flask": "flask" in combined,
        "django": "django" in combined,
        "fastapi": "fastapi" in combined,
        "node": language in ["javascript", "typescript"] or any(k in combined for k in ["node", "react", "next", "vue", "express"]),
        "react": "react" in combined,
        "vite": "vite" in combined,
        "docker": "docker" in combined or "dockerfile" in combined,
    }
    return {k: v for k, v in detected.items() if k in allowed_keys}


def validate_yaml(yaml_content: str) -> List[str]:
    errors = []
    try:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            return ["YAML content must produce a top-level dictionary"]
        if "name" not in data:
            errors.append("Missing required root field: 'name'")
        if "on" not in data:
            errors.append("Missing required root field: 'on'")
        if "jobs" not in data or not isinstance(data.get("jobs"), dict):
            errors.append("Missing required root dictionary: 'jobs'")
    except Exception as exc:
        errors.append(f"Invalid YAML syntax: {exc}")
    return errors


def _cache_key(repo_id: int) -> str:
    return f"workflow_analysis:{repo_id}"


class WorkflowEngine:
    def __init__(self, current_user: User, github_service: GitHubService, cache_service: Optional[CacheService] = None):
        self.user = current_user
        self.github = github_service
        self.cache = cache_service or CacheService()

    def get_available_templates(self) -> List[str]:
        return list(GitHubService.get_templates().keys())

    def analyze_repository(self, repo_id: int) -> dict:
        cached = self.cache.get(_cache_key(repo_id))
        if cached:
            logger.info("Cache hit for repository analysis repo_id=%s", repo_id)
            value = cached.decode("utf-8") if isinstance(cached, bytes) else cached
            return json.loads(value)

        repo = db.session.get(Repository, repo_id)
        if not repo:
            raise WorkflowEngineError(f"Repository {repo_id} not found")

        repo_data = self.github.get_repository(repo.full_name)
        if not repo_data:
            raise WorkflowEngineError("Failed to fetch repository from GitHub")

        tech_stack = detect_tech_stack(repo_data)
        result = {
            "repository_id": repo_id,
            "repo_name": repo.name,
            "detected": tech_stack,
            "github_url": repo_data.get("html_url"),
        }

        self.cache.set(_cache_key(repo_id), json.dumps(result), expire=600)
        logger.info("Analyzed repository_id=%s – stack=%s", repo_id, tech_stack)
        return result

    def generate_workflow(self, repo_id: int, workflow_name: str, stack: str, branch: Optional[str] = None) -> dict:
        repo = db.session.get(Repository, repo_id)
        if not repo:
            raise WorkflowEngineError(f"Repository {repo_id} not found")

        if stack not in self.get_available_templates():
            raise WorkflowEngineError("Unsupported workflow stack", errors=[f"Supported stacks: {', '.join(self.get_available_templates())}"])

        target_branch = branch or repo.default_branch or "main"
        yaml_content = GitHubService.generate_workflow_template(stack, workflow_name, target_branch)
        validation_errors = validate_yaml(yaml_content)
        if validation_errors:
            raise WorkflowEngineError("Generated workflow is invalid", errors=validation_errors)

        return {"yaml": yaml_content, "branch": target_branch}

    def commit_workflow(self, repo_id: int, workflow_name: str, stack: str, commit_message: str, branch: Optional[str] = None) -> dict:
        repo = db.session.get(Repository, repo_id)
        if not repo:
            raise WorkflowEngineError(f"Repository {repo_id} not found")

        target_branch = branch or repo.default_branch or "main"
        generated = self.generate_workflow(repo_id, workflow_name, stack, target_branch)
        response = self.github.commit_workflow_file(
            repo_full_name=repo.full_name,
            branch=target_branch,
            file_path="pipeline.yml",
            commit_message=commit_message,
            yaml_content=generated["yaml"],
            author_name=self.user.name if self.user else "Pipeline.sh",
            author_email=self.user.email if self.user else "pipeline@example.com",
        )

        if not response or response.get("error") or not response.get("html_url"):
            raise WorkflowEngineError("Failed to commit workflow to GitHub", errors=[response.get("error", "GitHub commit returned an empty response")])

        self.cache.delete(_cache_key(repo_id))
        logger.info("Committed workflow for repository_id=%s to %s@%s", repo_id, repo.full_name, target_branch)
        return {"github_url": response.get("html_url", "")}
