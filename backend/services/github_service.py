import requests
import yaml


class GitHubService:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def list_user_repositories(self):
        url = "https://api.github.com/user/repos?per_page=100"
        resp = requests.get(url, headers=self.headers)
        return resp.json() if resp.ok else []

    def get_repository(self, full_name: str):
        url = f"https://api.github.com/repos/{full_name}"
        resp = requests.get(url, headers=self.headers)
        return resp.json() if resp.ok else None

    @staticmethod
    def generate_workflow_template(project_type: str, workflow_name: str, branch: str):
        templates = {
            "python": {
                "name": workflow_name,
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
            "flask": {
                "name": workflow_name,
                "on": ["push", "pull_request"],
                "jobs": {
                    "ci": {
                        "runs-on": "ubuntu-latest",
                        "steps": [
                            {"uses": "actions/checkout@v4"},
                            {"name": "Set up Python", "uses": "actions/setup-python@v5", "with": {"python-version": "3.11"}},
                            {"name": "Install requirements", "run": "pip install -r requirements.txt"},
                            {"name": "Run lint", "run": "flake8 ."},
                            {"name": "Run tests", "run": "pytest"},
                        ],
                    }
                },
            },
            "docker": {
                "name": workflow_name,
                "on": ["push"],
                "jobs": {
                    "build": {
                        "runs-on": "ubuntu-latest",
                        "steps": [
                            {"uses": "actions/checkout@v4"},
                            {"name": "Build Docker image", "run": "docker build -t pipeline-sh-app ."},
                            {"name": "Push artifact", "run": "echo 'Docker image built'"},
                        ],
                    }
                },
            },
            "ai": {
                "name": workflow_name,
                "on": ["push"],
                "jobs": {
                    "train": {
                        "runs-on": "ubuntu-latest",
                        "steps": [
                            {"uses": "actions/checkout@v4"},
                            {"name": "Set up Python", "uses": "actions/setup-python@v5", "with": {"python-version": "3.11"}},
                            {"name": "Install dependencies", "run": "pip install -r requirements.txt"},
                            {"name": "Run model training", "run": "python backend/services/tf_predictor.py"},
                        ],
                    }
                },
            },
        }
        payload = templates.get(project_type, templates["python"])
        return yaml.dump(payload, sort_keys=False)
