# API Specification - CI/CD Pipeliner

This document reflects the actual backend endpoints currently implemented in the Flask app.

## General Principles
*   **Base URL:** `/api`
*   **Authentication:** JWT HttpOnly cookie or authenticated request headers.
*   **Authorization:** Ownership and admin checks are enforced by route handlers.
*   **Status Codes:** Standard HTTP status codes (200 OK, 201 Created, 202 Accepted, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 500 Internal Server Error).

## 1. Authentication & Users (`/api/auth`)
*   `POST /api/auth/register` - Register a new local user.
*   `POST /api/auth/login` - Authenticate a local user and set JWT cookie.
*   `POST /api/auth/logout` - Clear the JWT cookie.
*   `GET /api/auth/me` - Get the current authenticated user's profile.
*   `POST /api/auth/verify-email` - Verify email with OTP.
*   `POST /api/auth/resend-otp` - Resend OTP for verification or password flow.
*   `GET /api/auth/github/callback` - OAuth callback redirect wiring (implemented through frontend flow).

## 2. OAuth & GitHub Integration (`/api/github`)
*   `GET /api/github/repos` - List repositories accessible by the connected GitHub account.
*   `POST /api/github/connect` - Connect a GitHub repository to the current project.
*   `POST /api/github/generate-workflow` - Produce a workflow template payload without committing.
*   `POST /api/github/webhook` - GitHub webhook receiver for push-triggered re-analysis.

## 3. Projects & Analysis (`/api/projects`)
*   `POST /api/projects` - Create a project from a GitHub repository URL.
*   `GET /api/projects` - List all projects for the authenticated user.
*   `GET /api/projects/<project_id>` - Get details for a project and associated workflow steps.
*   `DELETE /api/projects/<project_id>` - Delete a project.
*   `GET /api/projects/<project_id>/status` - Poll project status.
*   `POST /api/projects/<project_id>/analyze` - Trigger a fresh repo analysis. Returns `202 Accepted`.
*   `PATCH /api/projects/<project_id>/steps` - Approve or reject generated steps.

## 4. Pipeline & Automation Generation (`/api/workflow`)
*   `GET /api/workflow/templates` - Return available workflow templates.
*   `POST /api/workflow/analyze` - Analyze repository technology stack.
*   `POST /api/workflow/generate` - Generate a workflow YAML.
*   `POST /api/workflow/preview` - Preview workflow without committing.
*   `POST /api/workflow/commit` - Commit the generated workflow to the repo.

## 5. Deployments (`/api/deploy`)
*   `POST /api/deploy/projects/<project_id>` - Start deployment for a given project.
*   `GET /api/deploy/all` - List recent deployments for the platform.

## 6. Admin & Analytics (`/api/admin`)
*   `GET /api/admin/stats` - Dashboard statistics for admin users.
*   `GET /api/admin/audit-logs` - Recent platform audit logs.

> Note: The route names in this document are aligned to the actual implementation in the current codebase. If the frontend or documentation uses older names, update them to match the endpoints above before testing the app in production.
