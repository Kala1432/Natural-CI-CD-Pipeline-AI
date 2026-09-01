# Pipeline.sh REST API

Base URL

```
/api
```

---

# Authentication

## POST

```
/auth/register
```

Register user.

## POST

```
/auth/login
```

Login user and set JWT cookie.

## POST

```
/auth/logout
```

Logout user.

## GET

```
/auth/me
```

Get the current authenticated user profile.

## POST

```
/auth/verify-email
```

Verify email using OTP.

---

# GitHub

## GET

```
/github/repos
```

List repositories accessible to the connected GitHub account.

## POST

```
/github/connect
```

Connect a repository to the current user project.

## POST

```
/github/generate-workflow
```

Generate a workflow template payload.

## POST

```
/github/webhook
```

Receive GitHub push webhook and trigger re-analysis.

---

# Projects

## POST

```
/projects
```

Create a project from a GitHub repo URL.

## GET

```
/projects
```

List projects for the authenticated user.

## GET

```
/projects/{project_id}
```

Get project details, steps, and workflow.

## GET

```
/projects/{project_id}/status
```

Check project analysis status.

## POST

```
/projects/{project_id}/analyze
```

Trigger a fresh project analysis.

---

# Workflow

## GET

```
/workflow/templates
```

Return workflow templates.

## POST

```
/workflow/analyze
```

Analyze repository tech stack.

## POST

```
/workflow/generate
```

Generate workflow YAML.

## POST

```
/workflow/preview
```

Preview generated workflow.

## POST

```
/workflow/commit
```

Commit workflow to the repository.

---

# Deployments

## POST

```
/deploy/projects/{project_id}
```

Start deployment for a project.

## GET

```
/deploy/all
```

List recent deployments.

---

# Admin

## GET

```
/admin/stats
```

View admin statistics.

## GET

```
/admin/audit-logs
```

View recent audit logs.

Repository details

---

## GET

```
/github/repos/{id}/branches
```

Repository branches

---

# Workflow

## POST

```
/workflow/analyze
```

Analyze repository

---

## POST

```
/workflow/generate
```

Generate workflow

---

## POST

```
/workflow/preview
```

Preview workflow

---

## POST

```
/workflow/commit
```

Commit workflow

---

# Pipeline

## GET

```
/pipeline/history
```

Execution history

---

## POST

```
/pipeline/trigger
```

Trigger pipeline

---

## POST

```
/pipeline/cancel
```

Cancel execution

---

## POST

```
/pipeline/rerun
```

Rerun pipeline

---

## GET

```
/pipeline/logs/{id}
```

Pipeline logs

---

# Analytics

## GET

```
/analytics/dashboard
```

Dashboard statistics

---

## GET

```
/analytics/repositories
```

Repository statistics

---

## GET

```
/analytics/pipelines
```

Pipeline analytics

---

# Standard Response

```json
{
  "success": true,
  "message": "Operation completed successfully.",
  "data": {}
}
```

---

# Error Response

```json
{
  "success": false,
  "message": "Description of error.",
  "data": null
}
```

---

# HTTP Status Codes

200 OK

201 Created

400 Bad Request

401 Unauthorized

403 Forbidden

404 Not Found

409 Conflict

422 Validation Error

429 Rate Limited

500 Internal Server Error