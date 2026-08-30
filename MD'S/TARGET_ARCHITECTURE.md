# Target Architecture - CI/CD Pipeliner

## Overview

The target architecture for CI/CD Pipeliner is designed to support a production-ready, AI-powered automation platform while remaining maintainable by a small engineering team. It embraces a monolithic approach for the core application (to reduce operational overhead) but delegates heavy workloads and background processing to asynchronous workers and external systems.

---

## 1. Component Architecture

### Frontend (React / Vite)
*   **Framework**: React 18+ with Vite.
*   **State Management**: React Context or Zustand for global state, React Query for server state and caching.
*   **Routing**: React Router.
*   **UI Library**: TailwindCSS for styling.
*   **Deployment**: Statically built and served by Nginx or a CDN (e.g., AWS CloudFront).

### Backend (Python / Flask)
*   **Framework**: Flask (Core API).
*   **Database ORM**: SQLAlchemy with Flask-Migrate.
*   **Authentication**: Flask-JWT-Extended (with HttpOnly cookies).
*   **Asynchronous Task Queue**: Celery (Background Workers).
*   **Message Broker & Cache**: Redis.
*   **Deployment**: Gunicorn + Gevent/Eventlet workers behind Nginx, containerized in Docker.

### Data Layer
*   **Primary Database**: PostgreSQL (Relational data, Users, Projects, Pipelines).
*   **Caching & Task Queue**: Redis (Session caching, Celery broker, Rate limiting).
*   **Blob Storage**: AWS S3 (Pipeline logs, generated artifacts, ML models).

### AI & ML Services
*   **Recommendation Engine**: OpenAI API (GPT-4o) accessed securely from the backend.
*   **Prediction Engine**: MLflow model registry, TensorFlow/Scikit-learn models executed within background Celery tasks.

---

## 2. Logical Modules

1.  **User Authentication Module**: Handles email/password registration, login, JWT token issuance, password resets, and email verification.
2.  **OAuth Authentication Module**: Manages secure connection to GitHub and Google, token exchange, and account linking.
3.  **User Management Module**: Manages user profiles, roles (User, Admin), and account status.
4.  **GitHub Integration Module**: Communicates with the GitHub API to fetch repository data, branches, file trees, and commit histories.
5.  **Repository Analyzer Module**: Inspects file trees to detect languages, frameworks, package managers, and testing tools.
6.  **Repository Intelligence Module**: Calculates the "Deployment Readiness Score" based on analysis results.
7.  **AI Recommendation Engine**: Prompts the LLM with repository context to generate CI/CD configuration files.
8.  **ML/Prediction Engine**: Analyzes historical pipeline data to predict failure probabilities and detect anomalies.
9.  **Docker Generator Module**: Constructs optimal `Dockerfile` and `.dockerignore` based on detected stack and best practices.
10. **GitHub Actions Generator Module**: Constructs optimal `.github/workflows/ci.yml` pipelines.
11. **Pipeline Validator Module**: Performs syntax and structural validation of generated Dockerfiles and YAML before presenting them to the user.
12. **Pull Request Manager Module**: Formats and submits the generated files to the user's GitHub repository as a Pull Request.
13. **Deployment Manager Module**: Manages the deployment lifecycle, interfacing with AWS EC2.
14. **AWS/EC2 Integration Module**: Securely provisions and communicates with EC2 instances for deployment.
15. **Deployment Monitoring Module**: Polls health endpoints of deployed applications and aggregates metrics.
16. **Incident Management Module**: Tracks deployment failures and anomalies, creating actionable incident reports.
17. **Rollback/Recovery Module**: Reverts EC2 instances to previous healthy images if a new deployment fails health checks.
18. **Admin Management Module**: Provides system-wide controls, user moderation, and role assignment.
19. **Audit Logging Module**: Records critical system events immutably to the database and external logging services.
20. **Notifications Module**: Sends emails and in-app alerts regarding pipeline status and incidents.

---

## 3. Data Flow

### Repository Analysis Flow
1.  **User Request**: User submits a GitHub Repository URL via the frontend.
2.  **API Gateway**: The request hits the Flask backend (`/api/projects/analyze`).
3.  **Task Queue**: Backend validates the request and enqueues an `analyze_repo` Celery task. The API returns `202 Accepted` with a task ID.
4.  **GitHub Integration**: Celery worker uses the user's GitHub OAuth token (or GitHub App token) to fetch the repository tree.
5.  **Repository Analyzer**: The worker parses the tree, identifying tech stacks (e.g., Python, FastAPI).
6.  **Database Update**: The worker updates the `Project` status to `analyzed` and writes `AutomationStep` records.
7.  **Client Polling**: The frontend polls the project status and displays the results when complete.

### AI Generation & PR Workflow
1.  **User Approval**: User approves the recommended steps on the frontend.
2.  **Task Queue**: Backend enqueues a generation task.
3.  **AI Recommendation Engine**: Celery worker queries the LLM with the repository context to generate `Dockerfile` and `ci.yml`.
4.  **Pipeline Validator**: The worker locally validates the syntax of the generated files.
5.  **Database Update**: The worker saves the generated content to `GeneratedWorkflow`.
6.  **User Review**: The frontend displays the generated files and diffs.
7.  **PR Creation**: User clicks "Create PR". Backend uses the GitHub API to create a new branch, commit the files, and open a PR.

### Deployment & Rollback Workflow
1.  **Webhook Trigger**: GitHub sends a webhook to the backend when a PR is merged or a push to `main` occurs.
2.  **GitHub Actions**: GitHub Actions runs the CI pipeline, builds the Docker image, and pushes it to a registry.
3.  **Deployment Trigger**: Upon successful CI, a CD step triggers the backend `/api/deploy` endpoint.
4.  **AWS Integration**: Celery worker connects to the target EC2 instance, pulls the new Docker image, and starts the container.
5.  **Health Check**: The `Deployment Monitoring Module` pings the container's health endpoint.
6.  **Failure Detection & Rollback**: If the health check fails or times out, the `Rollback Module` is triggered. The previous container is restarted, an `Incident` is logged, and the `Deployment` is marked as failed.

---

## 4. Security Boundaries

*   **Network Isolation**: The PostgreSQL database and Redis cache must be isolated within a private subnet, inaccessible from the public internet. Only the Flask application and Celery workers can communicate with them.
*   **Authentication Boundary**: All API routes under `/api/` (except public login/registration) are protected by JWT middleware. Admin routes (`/api/admin/`) require explicit admin role verification.
*   **External Integrations**: All communication with GitHub, OpenAI, and AWS occurs over TLS. Credentials and API keys are stored in a secure secret manager, injected at runtime, and never hardcoded.
*   **Execution Isolation**: User-provided code (from repositories) is never executed natively on the backend servers. Any necessary parsing or validation happens statically or within tightly locked-down sandboxes (e.g., gVisor containers) if execution is strictly required.
