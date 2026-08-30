import base64
import logging
import time
import requests
import yaml

logger = logging.getLogger(__name__)


class GitHubService:
    BASE = "https://api.github.com"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, url: str, params: dict = None):
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=15)
            if resp.status_code == 403:
                logger.warning("GitHub 403 on %s — rate limit or permissions", url)
            return resp
        except requests.RequestException as exc:
            logger.error("GitHub request failed: %s", exc)
            return None

    def list_user_repositories(self):
        resp = self._get(f"{self.BASE}/user/repos", params={"per_page": 100, "sort": "updated"})
        return resp.json() if resp and resp.ok else []

    def get_repository(self, full_name: str):
        resp = self._get(f"{self.BASE}/repos/{full_name}")
        return resp.json() if resp and resp.ok else None

    def wait_for_repository(self, owner: str, repo: str, timeout: int = 15) -> bool:
        """Poll GitHub API until the repository exists and is accessible."""
        start = time.time()
        while time.time() - start < timeout:
            repo_info = self.get_repository(f"{owner}/{repo}")
            if repo_info and not repo_info.get("message"):
                return True
            time.sleep(1.5)
        return False

    def get_repo_tree(self, owner: str, repo: str, branch: str) -> dict | None:
        """Fetch the full recursive file tree for a repo branch."""
        resp = self._get(
            f"{self.BASE}/repos/{owner}/{repo}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        if not resp or not resp.ok:
            logger.warning("get_repo_tree failed for %s/%s@%s: %s",
                           owner, repo, branch, resp.status_code if resp else "no response")
            return None
        return resp.json()

    def get_file_content(self, owner: str, repo: str, path: str, branch: str) -> str | None:
        """Fetch and decode a single file's text content."""
        resp = self._get(
            f"{self.BASE}/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        if not resp or not resp.ok:
            return None
        data = resp.json()
        if isinstance(data, dict) and data.get("encoding") == "base64":
            try:
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            except Exception:
                return None
        return None

    def commit_workflow_file(self, repo_full_name: str, branch: str, file_path: str, commit_message: str, yaml_content: str, author_name: str = None, author_email: str = None):
        clean_path = file_path.lstrip("/")
        url = f"{self.BASE}/repos/{repo_full_name}/contents/{clean_path}"
        content = base64.b64encode(yaml_content.encode("utf-8")).decode("utf-8")
        payload = {
            "message": commit_message,
            "content": content,
            "branch": branch,
        }
        if author_name and author_email and "@" in author_email:
            payload["committer"] = {"name": author_name, "email": author_email}
            payload["author"] = {"name": author_name, "email": author_email}

        existing = requests.get(url, headers=self.headers, params={"ref": branch}, timeout=15)
        if existing.ok and isinstance(existing.json(), dict):
            payload["sha"] = existing.json().get("sha")

        resp = requests.put(url, headers=self.headers, json=payload, timeout=15)
        if resp.ok:
            return resp.json()
        else:
            try:
                err_json = resp.json()
                err_msg = err_json.get("message", resp.text)
                if "errors" in err_json and isinstance(err_json["errors"], list):
                    details = [e.get("message", "") for e in err_json["errors"] if e.get("message")]
                    if details:
                        err_msg += ": " + ", ".join(details)
            except Exception:
                err_msg = resp.text

            if resp.status_code == 404:
                err_msg = f"Target repository or branch '{branch}' was not found on GitHub ({repo_full_name})."

            logger.error("commit_workflow_file failed on %s@%s: %s (status %s)", repo_full_name, branch, err_msg, resp.status_code)
            return {"error": err_msg, "status_code": resp.status_code}

    def commit_file(self, repo_full_name: str, branch: str, file_path: str, commit_message: str, file_content: str, author_name: str = None, author_email: str = None):
        """Wrapper around commit_workflow_file for general file modification."""
        return self.commit_workflow_file(repo_full_name, branch, file_path, commit_message, file_content, author_name, author_email)

    def get_workflow_runs(self, owner: str, repo: str, branch: str) -> dict | None:
        """Fetch recent workflow runs for a specific branch."""
        url = f"{self.BASE}/repos/{owner}/{repo}/actions/runs"
        resp = self._get(url, params={"branch": branch, "per_page": 5})
        if not resp or not resp.ok:
            return None
        return resp.json()

    def get_workflow_run_logs(self, owner: str, repo: str, run_id: int) -> str | None:
        """Download and return the logs for a specific workflow run.
        GitHub Actions returns a zip file of logs, but we just need a snippet for AI if possible, 
        or we can fetch the jobs and then the job logs.
        Wait, fetching the raw text log of a job is easier than the whole run zip.
        """
        jobs_url = f"{self.BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        jobs_resp = self._get(jobs_url)
        if not jobs_resp or not jobs_resp.ok:
            return None
            
        jobs_data = jobs_resp.json()
        jobs = jobs_data.get("jobs", [])
        
        all_logs = []
        for job in jobs:
            job_id = job.get("id")
            log_url = f"{self.BASE}/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
            # Getting job logs requires following a redirect (which requests does automatically)
            # but we need to accept text/plain
            try:
                log_resp = requests.get(log_url, headers={"Authorization": f"Bearer {self.token}"}, timeout=15)
                if log_resp.ok:
                    all_logs.append(f"--- LOGS FOR JOB: {job.get('name')} ---\n" + log_resp.text[-5000:])
            except Exception as e:
                logger.error("Failed to fetch log for job %s: %s", job_id, e)
                
        return "\n".join(all_logs) if all_logs else None

    @staticmethod
    def get_templates():
        return {
            "python": {
                "name": "pipeline-sh-ci",
                "on": ["push", "pull_request"],
                "jobs": {
                    "build": {
                        "runs-on": "ubuntu-latest",
                        "steps": [
                            {"uses": "actions/checkout@v4"},
                            {"name": "Set up Python", "uses": "actions/setup-python@v5", "with": {"python-version": "3.11"}},
                            {"name": "Install dependencies", "run": "pip install -r requirements.txt"},
                            {"name": "Run tests", "run": "pytest"},
                        ],
                    }
                },
            },
            "docker": {
                "name": "pipeline-sh-ci",
                "on": ["push"],
                "jobs": {
                    "build": {
                        "runs-on": "ubuntu-latest",
                        "steps": [
                            {"uses": "actions/checkout@v4"},
                            {"name": "Build Docker image", "run": "docker build -t pipeline-sh-app ."},
                        ],
                    }
                },
            },
        }

    @staticmethod
    def generate_workflow_template(project_type: str, workflow_name: str, branch: str):
        templates = GitHubService.get_templates()
        payload = templates.get(project_type, templates["python"])
        payload = dict(payload)
        payload["name"] = workflow_name
        payload["on"] = ["push", "pull_request"] if project_type != "docker" else ["push"]
        return yaml.dump(payload, sort_keys=False)

    def get_authenticated_user(self) -> dict | None:
        """Get the current authenticated user's profile."""
        resp = self._get(f"{self.BASE}/user")
        return resp.json() if resp and resp.ok else None

    def fork_repository(self, owner: str, repo: str) -> dict:
        """Fork a repository into the authenticated user's GitHub account and poll until ready."""
        url = f"{self.BASE}/repos/{owner}/{repo}/forks"
        try:
            resp = requests.post(url, headers=self.headers, timeout=20)
            if resp.ok or resp.status_code == 202:
                fork_data = resp.json()
                logger.info("Successfully requested fork for %s/%s", owner, repo)
                user_info = self.get_authenticated_user()
                if user_info and user_info.get("login"):
                    self.wait_for_repository(user_info["login"], repo, timeout=15)
                return fork_data
            err_msg = resp.json().get("message") if resp.content else resp.text
            logger.error("Failed to fork %s/%s: %s", owner, repo, err_msg)
            return {"error": err_msg}
        except Exception as exc:
            logger.error("Fork Exception: %s", exc)
            return {"error": str(exc)}

    def create_branch(self, owner: str, repo: str, new_branch: str, base_branch: str) -> dict:
        """Create a new git branch in the repository pointing to the base branch's latest commit."""
        # 1. Get SHA of base branch (with automatic fallback for main/master/dev)
        ref_url = f"{self.BASE}/repos/{owner}/{repo}/git/ref/heads/{base_branch}"
        resp = self._get(ref_url)

        if not resp or not resp.ok:
            repo_info = self.get_repository(f"{owner}/{repo}")
            actual_default = repo_info.get("default_branch") if repo_info else None
            if actual_default and actual_default != base_branch:
                ref_url = f"{self.BASE}/repos/{owner}/{repo}/git/ref/heads/{actual_default}"
                resp = self._get(ref_url)

        if not resp or not resp.ok:
            for alt_branch in ["main", "master", "dev", "development"]:
                if alt_branch != base_branch:
                    ref_url = f"{self.BASE}/repos/{owner}/{repo}/git/ref/heads/{alt_branch}"
                    resp = self._get(ref_url)
                    if resp and resp.ok:
                        break

        if not resp or not resp.ok:
            err_msg = resp.json().get("message") if resp and resp.content else (resp.text if resp else "Could not fetch base branch reference")
            logger.error("Failed to fetch base branch ref for %s/%s: %s", owner, repo, err_msg)
            return {"error": err_msg, "status_code": resp.status_code if resp else 500}

        sha = resp.json().get("object", {}).get("sha")
        if not sha:
            return {"error": "Could not find commit SHA for base branch"}

        # 2. Create the new ref
        create_url = f"{self.BASE}/repos/{owner}/{repo}/git/refs"
        payload = {
            "ref": f"refs/heads/{new_branch}",
            "sha": sha
        }

        # Check if the branch already exists to avoid 422 error
        check_url = f"{self.BASE}/repos/{owner}/{repo}/git/ref/heads/{new_branch}"
        check_resp = self._get(check_url)
        if check_resp and check_resp.ok:
            logger.info("Branch %s already exists in %s/%s", new_branch, owner, repo)
            return {"ref": f"refs/heads/{new_branch}", "sha": sha, "already_exists": True}

        post_resp = requests.post(create_url, headers=self.headers, json=payload, timeout=15)
        if post_resp.ok:
            logger.info("Successfully created branch %s in %s/%s", new_branch, owner, repo)
            return post_resp.json()
        else:
            err_msg = post_resp.json().get("message") if post_resp.content else post_resp.text
            logger.error("Failed to create branch in %s/%s: %s", owner, repo, err_msg)
            return {"error": err_msg, "status_code": post_resp.status_code}

    def get_existing_pull_request(self, owner: str, repo: str, head_branch: str) -> dict | None:
        """Find an open pull request matching a specific head branch or ref."""
        url = f"{self.BASE}/repos/{owner}/{repo}/pulls"
        # 1. Try head parameter directly
        resp = self._get(url, params={"head": head_branch, "state": "open"})
        if resp and resp.ok:
            prs = resp.json()
            if isinstance(prs, list) and len(prs) > 0:
                return prs[0]

        # 2. Try owner:head_branch format
        if ":" not in head_branch:
            resp = self._get(url, params={"head": f"{owner}:{head_branch}", "state": "open"})
            if resp and resp.ok:
                prs = resp.json()
                if isinstance(prs, list) and len(prs) > 0:
                    return prs[0]

        # 3. Fallback: list open PRs and match head.ref
        resp = self._get(url, params={"state": "open", "per_page": 50})
        if resp and resp.ok:
            prs = resp.json()
            if isinstance(prs, list):
                clean_ref = head_branch.split(":")[-1]
                for pr in prs:
                    if pr.get("head", {}).get("ref") == clean_ref:
                        return pr
        return None

    def create_pull_request(self, owner: str, repo: str, title: str, head_branch: str, base_branch: str, body: str) -> dict:
        """Open a new Pull Request on GitHub."""
        url = f"{self.BASE}/repos/{owner}/{repo}/pulls"
        payload = {
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body
        }
        resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
        if resp.ok:
            logger.info("Successfully created PR for %s/%s: %s", owner, repo, resp.json().get("html_url"))
            return resp.json()
        else:
            try:
                err_json = resp.json()
                err_msg = err_json.get("message", resp.text)
                if "errors" in err_json and isinstance(err_json["errors"], list):
                    details = [e.get("message", "") for e in err_json["errors"] if e.get("message")]
                    if details:
                        err_msg += ": " + ", ".join(details)
            except Exception:
                err_msg = resp.text
            logger.error("Failed to create PR for %s/%s: %s", owner, repo, err_msg)
            return {"error": err_msg, "status_code": resp.status_code}
