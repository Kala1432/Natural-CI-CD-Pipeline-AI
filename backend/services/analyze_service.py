import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.celery_app import celery_app
from flask import current_app, has_app_context

from backend.repositories import ProjectRepository, AutomationStepRepository
from backend.models_mongo import Project, DetectedStack

def _get_app():
    if has_app_context():
        return current_app._get_current_object()
    from backend.app import create_app
    return create_app()

logger = logging.getLogger(__name__)


def _set_status(project_id: str, status: str, error: str = None):
    """Update project status inside an app context."""
    app = _get_app()
    with app.app_context():
        project_repo = ProjectRepository()
        project_repo.update_status(project_id, status, error_message=error or "")


def _fetch_files_parallel(gh, owner, repo, branch, paths: list) -> dict:
    """
    Fetch multiple files from GitHub in parallel using a thread pool.
    Returns {path: content} for any files that were fetched successfully.
    """
    results = {}
    if not paths:
        return results
    with ThreadPoolExecutor(max_workers=min(4, len(paths))) as ex:
        future_to_path = {
            ex.submit(gh.get_file_content, owner, repo, p, branch): p
            for p in paths
        }
        for fut in as_completed(future_to_path, timeout=15):
            path = future_to_path[fut]
            try:
                content = fut.result()
                if content:
                    results[path] = content
            except Exception as exc:
                logger.warning("[analyze] failed to fetch %s: %s", path, exc)
    return results


def _save_stack_and_steps(project_id: str, stack: dict, steps: list):
    """Persist detected_stack and AutomationStep records."""
    app = _get_app()
    with app.app_context():
        project_repo = ProjectRepository()
        step_repo = AutomationStepRepository()

        # Build DetachedStack for MongoEngine
        detected_stack = DetectedStack(
            language=stack.get("language", ""),
            framework=stack.get("framework", ""),
            package_manager=stack.get("package_manager", ""),
            has_dockerfile=stack.get("has_dockerfile", False),
            has_tests=stack.get("has_tests", False),
        )

        project_repo.update_status(
            project_id,
            "analyzed",
            detected_stack=detected_stack.to_dict() if hasattr(detected_stack, 'to_dict') else {
                "language": stack.get("language", ""),
                "framework": stack.get("framework", ""),
                "package_manager": stack.get("package_manager", ""),
                "has_dockerfile": stack.get("has_dockerfile", False),
                "has_tests": stack.get("has_tests", False),
            },
            readiness_score=stack.get("readiness_score", 0),
        )

        # Remove any previous steps (re-analysis)
        from backend.models_mongo import AutomationStep
        AutomationStep.objects(project_id=project_id).delete()

        for s in steps:
            step_repo.create(
                project_id=project_id,
                step_key=s["step_key"],
                title=s["title"],
                description=s["description"],
                recommended=s["recommended"],
                yaml_snippet_preview=s.get("yaml_snippet_preview", ""),
            )

        project_repo.update_status(project_id, "awaiting_approval")


# Signal files that indicate a recognisable tech stack
_SIGNAL_FILES = {
    "package.json", "requirements.txt", "pyproject.toml", "setup.py",
    "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Gemfile",
}


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180)
def analyze_repo(self, project_id: str, github_token: str):
    """
    Background function: fetch repo tree, detect stack from real files,
    generate AutomationStep records with per-repo reasoning.
    Updates Project.status at each stage so the frontend can poll progress.

    Time limits (seconds):
      soft_time_limit=120: raises SoftTimeLimitExceeded after 2 min
      time_limit=180: hard kill after 3 min
    """
    import time as _time
    from backend.services.github_service import GitHubService
    try:
        t_start = _time.monotonic()
        app = _get_app()
        with app.app_context():
            from backend.repositories import ProjectRepository
            project_repo = ProjectRepository()
            project = project_repo.get_by_id(project_id)
            if not project:
                return
            owner = project.repo_owner
            repo = project.repo_name
            branch = project.default_branch or "main"

        gh = GitHubService(github_token)

        # ── Stage 1: Reading repo tree ──────────────────────────────────────
        _set_status(project_id, "pending_analysis")
        logger.info("[analyze] %s/%s — fetching tree", owner, repo)

        t0 = _time.monotonic()
        tree_data = gh.get_repo_tree(owner, repo, branch)
        logger.info("[analyze] tree fetched in %.2fs", _time.monotonic() - t0)
        if tree_data is None:
            # None means a network/auth error from _get()
            _set_status(project_id, "failed",
                        "Could not fetch repository tree. Check token permissions.")
            return

        if isinstance(tree_data, dict) and "message" in tree_data and "rate limit" in tree_data["message"].lower():
            _set_status(project_id, "failed",
                        "GitHub API rate limit exceeded. Please wait a few minutes and try again.")
            return

        tree_items = tree_data.get("tree", [])
        truncated = tree_data.get("truncated", False)

        if not tree_items:
            _set_status(project_id, "failed",
                        "Repository appears to be empty — no files found.")
            return

        filenames = {item["path"] for item in tree_items if item.get("type") == "blob"}

        # ── Stage 2: Detecting tech stack ───────────────────────────────────
        _set_status(project_id, "analyzed")
        logger.info("[analyze] %s/%s — detecting stack (%d files%s)",
                    owner, repo, len(filenames), ", truncated" if truncated else "")

        t1 = _time.monotonic()
        stack, file_contents = _detect_stack(gh, owner, repo, branch, filenames)
        stack["readiness_score"] = _calculate_readiness_score(stack)
        logger.info("[analyze] stack detected in %.2fs", _time.monotonic() - t1)

        if truncated:
            # Surface truncation as a warning in the first step description later
            stack["_truncated"] = True

        # ── Stage 3: Generating step suggestions ────────────────────────────
        t2 = _time.monotonic()
        steps = _generate_steps(stack, file_contents, filenames, owner, repo)
        logger.info("[analyze] steps generated in %.2fs (%d steps)", _time.monotonic() - t2, len(steps))

        # ── Persist ─────────────────────────────────────────────────────────
        _save_stack_and_steps(project_id, stack, steps)
        logger.info("[analyze] %s/%s — done, %.2fs total", owner, repo, _time.monotonic() - t_start)

    except Exception as exc:
        logger.exception("[analyze] project_id=%s failed: %s", project_id, exc)
        _set_status(project_id, "failed", str(exc))


# ── Stack detection ──────────────────────────────────────────────────────────

def _detect_stack(gh, owner: str, repo: str, branch: str, filenames: set) -> tuple[dict, dict]:
    """
    Read key signal files and return (stack_dict, file_contents_dict).
    stack_dict keys: language, framework, package_manager, has_dockerfile,
                     has_tests, has_ci, node_version, python_version,
                     test_framework, lint_config
    """
    contents = {}
    stack = {
        "language": None,
        "framework": None,
        "package_manager": None,
        "has_dockerfile": False,
        "has_tests": False,
        "has_ci": False,
        "node_version": None,
        "python_version": None,
        "test_framework": None,
        "lint_config": None,
    }

    # ── Existing CI ──────────────────────────────────────────────────────────
    ci_files = [f for f in filenames if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))]
    if ci_files:
        stack["has_ci"] = True

    # ── Dockerfile & Compose ──────────────────────────────────────────────────
    if "Dockerfile" in filenames or "dockerfile" in filenames:
        stack["has_dockerfile"] = True

    if "docker-compose.yml" in filenames or "docker-compose.yaml" in filenames:
        stack["has_docker_compose"] = True

    # ── Determine which files need fetching (parallel I/O) ────────────────────
    files_to_fetch = []
    if "package.json" in filenames:
        files_to_fetch.append("package.json")
    if "pyproject.toml" in filenames:
        files_to_fetch.append("pyproject.toml")
    if "requirements.txt" in filenames:
        files_to_fetch.append("requirements.txt")
    if "Gemfile" in filenames:
        files_to_fetch.append("Gemfile")

    # Fetch all relevant files in parallel — saves 2-4 seconds vs sequential calls
    fetched = _fetch_files_parallel(gh, owner, repo, branch, files_to_fetch)
    contents.update(fetched)

    # ── Node / JavaScript / TypeScript ───────────────────────────────────────
    if "package.json" in filenames:
        raw = fetched.get("package.json")
        if raw:
            try:
                pkg = json.loads(raw)
            except Exception:
                pkg = {}

            stack["language"] = "javascript"
            stack["package_manager"] = "npm"

            # Detect yarn / pnpm
            if "yarn.lock" in filenames:
                stack["package_manager"] = "yarn"
            elif "pnpm-lock.yaml" in filenames:
                stack["package_manager"] = "pnpm"

            # Node version from engines field
            engines = pkg.get("engines", {})
            if engines.get("node"):
                stack["node_version"] = engines["node"]

            # TypeScript
            if "tsconfig.json" in filenames or "typescript" in pkg.get("devDependencies", {}):
                stack["language"] = "typescript"

            # Framework detection from dependencies
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                stack["framework"] = "nextjs"
            elif "react" in deps:
                stack["framework"] = "react"
            elif "vue" in deps:
                stack["framework"] = "vue"
            elif "express" in deps:
                stack["framework"] = "express"
            elif "fastify" in deps:
                stack["framework"] = "fastify"
            elif "@nestjs/core" in deps:
                stack["framework"] = "nestjs"

            # Test framework
            scripts = pkg.get("scripts", {})
            if "jest" in deps or "jest" in scripts.get("test", ""):
                stack["test_framework"] = "jest"
                stack["has_tests"] = True
            elif "vitest" in deps:
                stack["test_framework"] = "vitest"
                stack["has_tests"] = True
            elif "mocha" in deps:
                stack["test_framework"] = "mocha"
                stack["has_tests"] = True
            elif scripts.get("test") and scripts["test"] not in ("echo \"Error: no test specified\" && exit 1", ""):
                stack["has_tests"] = True

    # ── Python ───────────────────────────────────────────────────────────────
    elif "requirements.txt" in filenames or "pyproject.toml" in filenames or "setup.py" in filenames:
        stack["language"] = "python"
        stack["package_manager"] = "pip"

        pyproject_raw = fetched.get("pyproject.toml")
        if pyproject_raw:
            if "poetry" in pyproject_raw:
                stack["package_manager"] = "poetry"
            if "pytest" in pyproject_raw:
                stack["test_framework"] = "pytest"
                stack["has_tests"] = True
            # Python version
            import re
            m = re.search(r'python_requires\s*=\s*["\']([^"\']+)["\']', pyproject_raw)
            if m:
                stack["python_version"] = m.group(1)

        requirements_raw = fetched.get("requirements.txt")
        if requirements_raw:
            lower = requirements_raw.lower()
            if "django" in lower:
                stack["framework"] = "django"
            elif "flask" in lower:
                stack["framework"] = "flask"
            elif "fastapi" in lower:
                stack["framework"] = "fastapi"
            if "pytest" in lower:
                stack["test_framework"] = "pytest"
                stack["has_tests"] = True

        # Check for test directories
        if any(f.startswith("tests/") or f.startswith("test/") for f in filenames):
            stack["has_tests"] = True
            if not stack["test_framework"]:
                stack["test_framework"] = "pytest"

    # ── Java ─────────────────────────────────────────────────────────────────
    elif "pom.xml" in filenames:
        stack["language"] = "java"
        stack["package_manager"] = "maven"
        stack["framework"] = "spring" if any("spring" in f for f in filenames) else None
        stack["has_tests"] = any(f.startswith("src/test/") for f in filenames)
        if stack["has_tests"]:
            stack["test_framework"] = "junit"

    elif "build.gradle" in filenames or "build.gradle.kts" in filenames:
        stack["language"] = "java"
        stack["package_manager"] = "gradle"
        stack["has_tests"] = any(f.startswith("src/test/") for f in filenames)
        if stack["has_tests"]:
            stack["test_framework"] = "junit"

    # ── Go ───────────────────────────────────────────────────────────────────
    elif "go.mod" in filenames:
        stack["language"] = "go"
        stack["package_manager"] = "go modules"
        stack["has_tests"] = any(f.endswith("_test.go") for f in filenames)
        if stack["has_tests"]:
            stack["test_framework"] = "go test"

    # ── Ruby ─────────────────────────────────────────────────────────────────
    elif "Gemfile" in filenames:
        stack["language"] = "ruby"
        stack["package_manager"] = "bundler"
        raw = fetched.get("Gemfile")
        if raw:
            if "rails" in raw.lower():
                stack["framework"] = "rails"
            if "rspec" in raw.lower():
                stack["test_framework"] = "rspec"
                stack["has_tests"] = True

    # ── Fallback: HTML / Static Web / Docker / General ─────────────────────────
    if not stack["language"]:
        html_files = [f for f in filenames if f.endswith(".html") or f.endswith(".htm")]
        if html_files or "index.html" in filenames:
            stack["language"] = "html"
            stack["framework"] = "static-web"
        elif stack["has_dockerfile"]:
            stack["language"] = "docker"
            stack["framework"] = "container"
        else:
            py_files = [f for f in filenames if f.endswith(".py")]
            js_files = [f for f in filenames if f.endswith(".js") or f.endswith(".ts")]
            if py_files:
                stack["language"] = "python"
                stack["framework"] = "script"
            elif js_files:
                stack["language"] = "javascript"
                stack["framework"] = "static-js"
            else:
                stack["language"] = "general"
                stack["framework"] = "code"

    # ── Lint config detection ─────────────────────────────────────────────────
    lint_files = {
        ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml",
        ".flake8", "setup.cfg", ".pylintrc", "golangci.yml", ".golangci.yml",
        "rubocop.yml", ".rubocop.yml",
    }
    found_lint = lint_files & filenames
    if found_lint:
        stack["lint_config"] = next(iter(found_lint))

    return stack, contents


def _calculate_readiness_score(stack: dict) -> int:
    """Calculate a 0-100 Deployment Readiness Score based on detected stack."""
    score = 0
    if stack.get("has_dockerfile"):
        score += 25
    if stack.get("has_tests"):
        score += 25
    if stack.get("has_ci"):
        score += 20
    if stack.get("lint_config"):
        score += 10
    if stack.get("package_manager"):
        score += 10
    if stack.get("has_docker_compose"):
        score += 10
    return min(100, score)


# ── Step generation ──────────────────────────────────────────────────────────

def _generate_steps(stack: dict, file_contents: dict, filenames: set, owner: str, repo: str) -> list:
    """
    Return a list of step dicts with per-repo reasoning in description.
    """
    steps = []
    lang = stack.get("language") or "unknown"
    framework = stack.get("framework")
    pm = stack.get("package_manager") or "npm"
    tf = stack.get("test_framework")
    has_tests = stack.get("has_tests", False)
    has_dockerfile = stack.get("has_dockerfile", False)
    has_ci = stack.get("has_ci", False)
    lint_config = stack.get("lint_config")
    node_ver = stack.get("node_version")
    py_ver = stack.get("python_version")

    # ── HTML / Static Web steps ─────────────────────────────────────────────
    if lang == "html" or framework == "static-web":
        steps.append({
            "step_key": "lint",
            "title": "Validate HTML & Web Assets",
            "description": (
                f"Detected HTML and static web assets in {owner}/{repo}. "
                f"Linting HTML files on every push ensures valid web structure and catches broken tags."
            ),
            "recommended": True,
            "yaml_snippet_preview": "- name: Validate HTML\n  run: npx htmlhint **/*.html || true",
        })
        steps.append({
            "step_key": "build",
            "title": "Verify Web Build Integrity",
            "description": (
                f"Verify that static web assets exist and are ready for deployment."
            ),
            "recommended": True,
            "yaml_snippet_preview": "- name: Verify HTML Files\n  run: test -f index.html && echo 'index.html verified'",
        })
        if has_dockerfile:
            steps.append({
                "step_key": "docker_build",
                "title": "Build Container Image",
                "description": f"Dockerfile found in {owner}/{repo}. Building container image for deployment.",
                "recommended": True,
                "yaml_snippet_preview": f"- run: docker build -t {repo.lower()} .",
            })
        steps.append({
            "step_key": "deploy",
            "title": "Deploy Static Site",
            "description": f"Deploy web assets to GitHub Pages or cloud hosting on main branch push.",
            "recommended": False,
            "yaml_snippet_preview": "- name: Deploy\n  run: echo 'Deploy static web assets'",
        })
        return steps

    # ── Lint step ────────────────────────────────────────────────────────────
    if lint_config:
        if lang in ("javascript", "typescript"):
            steps.append({
                "step_key": "lint",
                "title": "Lint with ESLint",
                "description": (
                    f"Found {lint_config} in {owner}/{repo} — ESLint is already configured. "
                    f"Adding a lint step using `{pm} run lint` on every PR will catch style and "
                    f"correctness issues before they reach main."
                ),
                "recommended": True,
                "yaml_snippet_preview": f"- run: {pm} run lint",
            })
        elif lang == "python":
            tool = "flake8" if ".flake8" in lint_config else "pylint"
            steps.append({
                "step_key": "lint",
                "title": f"Lint with {tool}",
                "description": (
                    f"Found {lint_config} in {owner}/{repo} — {tool} is configured. "
                    f"Running `{tool} .` on every push will enforce the project's existing "
                    f"style rules and catch common Python errors early."
                ),
                "recommended": True,
                "yaml_snippet_preview": f"- run: {tool} .",
            })
        elif lang == "go":
            steps.append({
                "step_key": "lint",
                "title": "Lint with golangci-lint",
                "description": (
                    f"Found {lint_config} in {owner}/{repo}. Running golangci-lint on every PR "
                    f"will enforce the project's Go linting rules."
                ),
                "recommended": True,
                "yaml_snippet_preview": "- uses: golangci/golangci-lint-action@v4",
            })
    elif lang in ("javascript", "typescript"):
        # Suggest lint even without config
        steps.append({
            "step_key": "lint",
            "title": "Lint with ESLint",
            "description": (
                f"No ESLint config found yet in {owner}/{repo}, but adding one is strongly "
                f"recommended for {lang} projects. This step will run `{pm} run lint` once "
                f"you add an .eslintrc file."
            ),
            "recommended": False,
            "yaml_snippet_preview": f"- run: {pm} run lint",
        })

    # ── Test step ────────────────────────────────────────────────────────────
    if has_tests and tf:
        if tf == "jest":
            install_cmd = f"{pm} ci" if pm == "npm" else f"{pm} install"
            steps.append({
                "step_key": "test",
                "title": "Run Jest tests",
                "description": (
                    f"Found Jest in {owner}/{repo}'s package.json. Running `{pm} test` on every "
                    f"push and PR ensures regressions are caught before merge."
                ),
                "recommended": True,
                "yaml_snippet_preview": f"- run: {install_cmd}\n      - run: {pm} test",
            })
        elif tf == "vitest":
            steps.append({
                "step_key": "test",
                "title": "Run Vitest tests",
                "description": (
                    f"Found Vitest in {owner}/{repo}'s package.json. Running `{pm} run test` "
                    f"on every push will validate your Vite-based test suite."
                ),
                "recommended": True,
                "yaml_snippet_preview": f"- run: {pm} run test",
            })
        elif tf == "pytest":
            install_cmd = "pip install -r requirements.txt" if "requirements.txt" in filenames else "pip install -e ."
            if pm == "poetry":
                install_cmd = "poetry install"
            steps.append({
                "step_key": "test",
                "title": "Run pytest",
                "description": (
                    f"Found pytest in {owner}/{repo}'s "
                    f"{'requirements.txt' if 'requirements.txt' in filenames else 'pyproject.toml'}. "
                    f"Running `pytest` on every push and PR will catch regressions in your "
                    f"{framework or 'Python'} application."
                ),
                "recommended": True,
                "yaml_snippet_preview": f"- run: {install_cmd}\n      - run: pytest",
            })
        elif tf == "go test":
            steps.append({
                "step_key": "test",
                "title": "Run Go tests",
                "description": (
                    f"Found *_test.go files in {owner}/{repo}. Running `go test ./...` on every "
                    f"push will validate all Go packages."
                ),
                "recommended": True,
                "yaml_snippet_preview": "- run: go test ./...",
            })
        elif tf == "junit":
            cmd = "mvn test" if pm == "maven" else "gradle test"
            steps.append({
                "step_key": "test",
                "title": f"Run JUnit tests ({pm})",
                "description": (
                    f"Found test sources under src/test/ in {owner}/{repo}. Running `{cmd}` "
                    f"on every push will execute the JUnit test suite."
                ),
                "recommended": True,
                "yaml_snippet_preview": f"- run: {cmd}",
            })
        elif tf in ("mocha", "rspec"):
            steps.append({
                "step_key": "test",
                "title": f"Run {tf} tests",
                "description": (
                    f"Found {tf} in {owner}/{repo}. Running tests on every push will catch "
                    f"regressions early."
                ),
                "recommended": True,
            })

    # ── Build step ───────────────────────────────────────────────────────────
    if lang in ("javascript", "typescript"):
        pkg_json = file_contents.get("package.json", "{}")
        try:
            pkg = json.loads(pkg_json)
        except Exception:
            pkg = {}
        scripts = pkg.get("scripts", {})
        if scripts.get("build"):
            install_cmd = f"{pm} ci" if pm == "npm" else f"{pm} install"
            steps.append({
                "step_key": "build",
                "title": f"Build ({pm} run build)",
                "description": (
                    f"Found a `build` script in {owner}/{repo}'s package.json "
                    f"(`{scripts['build']}`). Running the build step on every push confirms "
                    f"the {framework or lang} app compiles without errors."
                ),
                "recommended": True,
                "yaml_snippet_preview": f"- run: {install_cmd}\n      - run: {pm} run build",
            })
    elif lang == "java":
        cmd = "mvn package -DskipTests" if pm == "maven" else "gradle build -x test"
        steps.append({
            "step_key": "build",
            "title": f"Build with {pm}",
            "description": (
                f"Detected a {pm} project in {owner}/{repo}. Running `{cmd}` on every push "
                f"verifies the project compiles and packages correctly."
            ),
            "recommended": True,
            "yaml_snippet_preview": f"- run: {cmd}",
        })
    elif lang == "go":
        steps.append({
            "step_key": "build",
            "title": "Build Go binary",
            "description": (
                f"Detected a Go module in {owner}/{repo} (go.mod present). Running `go build ./...` "
                f"on every push confirms the project compiles cleanly."
            ),
            "recommended": True,
            "yaml_snippet_preview": "- run: go build ./...",
        })

    # ── Docker build step ────────────────────────────────────────────────────
    if has_dockerfile:
        steps.append({
            "step_key": "docker_build",
            "title": "Build Docker image",
            "description": (
                f"Found a Dockerfile in {owner}/{repo}. Building the Docker image on every push "
                f"catches container configuration errors early and ensures the image builds "
                f"successfully before any deployment."
            ),
            "recommended": True,
            "yaml_snippet_preview": f"- run: docker build -t {repo.lower()} .",
        })

    # ── Deploy step (suggested, not recommended by default) ──────────────────
    steps.append({
        "step_key": "deploy",
        "title": "Deploy to staging",
        "description": (
            f"Optional: add an automated deploy step for {owner}/{repo} that triggers on pushes "
            f"to the default branch. Configure your target environment (AWS, Heroku, Fly.io, etc.) "
            f"to enable this step."
        ),
        "recommended": False,
        "yaml_snippet_preview": None,
    })

    # ── Deploy step always gets a yaml_snippet_preview ──────────────────────
    # (already appended above — patch it in place)
    for s in steps:
        if s["step_key"] == "deploy" and not s.get("yaml_snippet_preview"):
            env_hint = "AWS_REGION" if lang in ("python", "java") else "FLY_API_TOKEN"
            s["yaml_snippet_preview"] = (
                f"- name: Deploy\n"
                f"  env:\n"
                f"    {env_hint}: ${{{{ secrets.{env_hint} }}}}\n"
                f"  run: echo 'Add your deploy command here'"
            )

    # ── Warn if CI already exists ─────────────────────────────────────────────
    if has_ci:
        if steps:
            steps[0]["description"] = (
                f"⚠️ Note: {owner}/{repo} already has GitHub Actions workflows in "
                f".github/workflows/. The steps below will create an additional workflow — "
                f"review for overlap before merging. " + steps[0]["description"]
            )

    # ── Warn if tree was truncated ────────────────────────────────────────────
    if stack.get("_truncated") and steps:
        steps[0]["description"] = (
            f"⚠️ Note: {owner}/{repo} has a very large file tree — GitHub returned a truncated "
            f"listing. Stack detection is based on the files that were visible. "
            + steps[0]["description"]
        )

    return steps
