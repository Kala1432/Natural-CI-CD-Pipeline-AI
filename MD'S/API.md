# API Specification - CI/CD Pipeliner

This document provides a high-level overview of the RESTful API routes provided by the Flask backend. All endpoints returning data return JSON format.

## General Principles
*   **Base URL:** `/api/v1` (versioning to be implemented)
*   **Authentication:** Endpoints requiring auth expect a JWT HttpOnly cookie.
*   **Authorization:** Endpoints verify ownership before returning resources.
*   **Status Codes:** Standard HTTP status codes (200 OK, 201 Created, 202 Accepted, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 500 Internal Server Error).

## 1. Authentication & Users (`/api/auth`)
*   `POST /api/auth/register` - Register a new local user.
*   `POST /api/auth/login` - Authenticate a local user and set JWT cookie.
*   `POST /api/auth/logout` - Clear the JWT cookie.
*   `GET /api/auth/me` - Get the current authenticated user's profile.
*   `POST /api/auth/verify-email` - Verify email using OTP.

## 2. OAuth & GitHub Integration (`/api/github`)
*   `GET /api/github/login` - Redirect to GitHub OAuth consent screen.
*   `GET /api/github/callback` - Handle OAuth callback and set JWT cookie.
*   `GET /api/github/repos` - Fetch repositories accessible by the connected GitHub account.

## 3. Projects & Analysis (`/api/projects`)
*   `POST /api/projects` - Connect a new repository to CI/CD Pipeliner.
*   `GET /api/projects` - List all projects owned by the user.
*   `GET /api/projects/:id` - Get details for a specific project.
*   `POST /api/projects/:id/analyze` - Trigger background analysis of the repository. Returns `202 Accepted`.
*   `GET /api/projects/:id/status` - Poll the status of an ongoing analysis.

## 4. Pipeline & Automation Generation (`/api/workflow`)
*   `POST /api/workflow/generate/:project_id` - Trigger LLM generation of Dockerfile and `ci.yml`. Returns `202 Accepted`.
*   `GET /api/workflow/:project_id` - View generated files and AI reasoning.
*   `POST /api/workflow/:project_id/pr` - Create a Pull Request in GitHub with the generated files.

## 5. Deployments (`/api/deploy`)
*   `POST /api/deploy/webhook` - Endpoint called by GitHub Actions upon successful CI build to trigger EC2 deployment.
*   `GET /api/deploy/:project_id` - List deployment history for a project.
*   `GET /api/deploy/:deployment_id/logs` - Fetch deployment logs.
*   `POST /api/deploy/:deployment_id/rollback` - Manually trigger a rollback.

## 6. Admin & Analytics (`/api/admin`) (Requires Admin Role)
*   `GET /api/admin/users` - List all users.
*   `PUT /api/admin/users/:id/role` - Change a user's role.
*   `GET /api/admin/metrics` - Fetch global metrics (total projects, deployment success rates).
*   `GET /api/admin/incidents` - List all system incidents.
