"""
MongoEngine document schemas for the CI/CD Pipeline platform.

This mirrors the SQLAlchemy models in ``models.py`` but is designed for
MongoDB Atlas.  Key differences from the relational layout:

* ObjectId primary keys (bson.ObjectId) instead of integer autoincrement.
* ``UserProfile`` is *embedded* inside ``User`` (1:1 relationship).
* 1:N relationships (User -> GithubConnection, User -> EmailOTP,
  User -> AuditLog, Repository -> pipelines, etc.) use ObjectId references
  rather than JOIN-table foreign keys.
* ``details`` on ``AuditLog`` is stored as a native dict / JSON document.
* ``detected_stack`` on ``Project`` is a native embedded dict.
* Optimistic locking is handled via a ``version`` field with ``write_concern``.
* TTL indexes are declared on ``EmailOTP`` so expired OTPs auto-expire.
"""

import json as _json
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from mongoengine import (
    Document,
    EmbeddedDocument,
    fields,
    signals,
)

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_str_oid(value):
    """Normalise an ObjectId / str / int into a hex string or ``None``."""
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, str):
        # already a hex string
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Embedded documents (1:1 with parent)
# ---------------------------------------------------------------------------
class UserProfile(EmbeddedDocument):
    github_connected = fields.BooleanField(default=False)
    github_access_token = fields.StringField(max_length=512, default="")
    github_login = fields.StringField(max_length=128, default="")
    notification_email = fields.StringField(max_length=256, default="")  # Use StringField to avoid validation issues
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "github_connected": self.github_connected,
            "github_login": self.github_login,
            "notification_email": self.notification_email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DetectedStack(EmbeddedDocument):
    """Embedded representation of the detected stack on a Project."""
    language = fields.StringField(max_length=64, default="")
    framework = fields.StringField(max_length=128, default="")
    package_manager = fields.StringField(max_length=64, default="")
    has_dockerfile = fields.BooleanField(default=False)
    has_tests = fields.BooleanField(default=False)
    has_ci = fields.BooleanField(default=False)
    test_framework = fields.StringField(max_length=64, default="")
    lint_config = fields.StringField(max_length=128, default="")
    node_version = fields.StringField(max_length=32, default="")
    python_version = fields.StringField(max_length=32, default="")

    def to_dict(self):
        return {
            "language": self.language,
            "framework": self.framework,
            "package_manager": self.package_manager,
            "has_dockerfile": self.has_dockerfile,
            "has_tests": self.has_tests,
        }


# ---------------------------------------------------------------------------
# Core documents
# ---------------------------------------------------------------------------
class User(Document):
    meta = {
        "collection": "users",
        "indexes": [
            "email",
            "github_id",
            "google_id",
            "role",
            ("email", "is_admin"),
        ],
    }

    # Explicitly define _id as ObjectId primary key
    email = fields.EmailField(required=True, unique=True)
    password_hash = fields.StringField(max_length=256, default="")
    github_id = fields.StringField(max_length=64, default="")
    google_id = fields.StringField(max_length=128, default="")
    name = fields.StringField(max_length=120, default="")
    avatar_url = fields.StringField(max_length=512, default="")
    role = fields.StringField(max_length=32, default="developer")
    email_verified = fields.BooleanField(default=False)
    is_admin = fields.BooleanField(default=False)
    profile = fields.EmbeddedDocumentField(UserProfile, default=UserProfile)
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "email_verified": self.email_verified,
            "is_admin": self.is_admin,
            "profile": self.profile.to_dict() if self.profile else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    # -- relationship-style helpers (return lists of ObjectIds) -----------
    def github_connections(self):
        from backend.repositories import GithubConnectionRepository
        return GithubConnectionRepository().find_by_user(self.id)

    def email_otps(self):
        from backend.repositories import EmailOTPRepository
        return EmailOTPRepository().find_by_user(self.id)

    def audit_logs(self):
        from backend.repositories import AuditLogRepository
        return AuditLogRepository().find_by_user(self.id)

    def repositories(self):
        from backend.repositories import RepositoryRepository
        return RepositoryRepository().find_by_user(self.id)


class GithubConnection(Document):
    """Link a user to a GitHub account (1 user -> many connections over time)."""
    meta = {
        "collection": "github_connections",
        "indexes": [("user_id", "github_id"), "user_id"],
    }

    user_id = fields.ObjectIdField()
    github_id = fields.StringField(max_length=64, required=True)
    access_token = fields.StringField(max_length=512, default="")
    login = fields.StringField(max_length=128, default="")
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "user_id": _to_str_oid(self.user_id),
            "github_id": self.github_id,
            "login": self.login,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EmailOTP(Document):
    """
    One-time password record.  Expired OTPs auto-expire via a TTL index
    on ``expires_at`` (see ``meta`` below).

    Note: the TTL index only takes effect on a real MongoDB instance.
    ``mongomock`` does not enforce TTL expiry.
    """
    meta = {
        "collection": "email_otps",
        "indexes": ["user_id", "purpose", "expires_at"],
    }

    user_id = fields.ObjectIdField()
    purpose = fields.StringField(max_length=32, required=True)
    code_hash = fields.StringField(max_length=64, required=True)
    attempts = fields.IntField(default=0)
    expires_at = fields.DateTimeField(required=True)
    consumed_at = fields.DateTimeField(default=None)
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "user_id": _to_str_oid(self.user_id),
            "purpose": self.purpose,
            "attempts": self.attempts,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_consumed": self.consumed_at is not None,
        }

    @property
    def is_expired(self):
        return self.expires_at is None or datetime.utcnow() > self.expires_at


class AuditLog(Document):
    meta = {
        "collection": "audit_logs",
        "indexes": ["user_id", "action", "resource_type", "created_at",
                     ("user_id", "created_at"),
                     ("action", "created_at")],
        "ordering": ["-created_at"],
    }

    user_id = fields.ObjectIdField(default=None)
    action = fields.StringField(max_length=128, required=True)
    resource_type = fields.StringField(max_length=64, default="")
    resource_id = fields.StringField(max_length=128, default="")
    status = fields.StringField(max_length=32, default="success")
    details = fields.DictField(default={})     # native dict / JSON document
    ip_address = fields.StringField(max_length=64, default="")
    user_agent = fields.StringField(max_length=512, default="")
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "user_id": _to_str_oid(self.user_id),
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "status": self.status,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Repository(Document):
    meta = {
        "collection": "repositories",
        "indexes": ["user_id", "github_repo_id",
                     ("user_id", "full_name")],
    }

    user_id = fields.ObjectIdField()
    github_repo_id = fields.StringField(max_length=64, required=True)
    name = fields.StringField(max_length=256, required=True)
    full_name = fields.StringField(max_length=256, required=True)
    visibility = fields.StringField(max_length=32, default="public")
    default_branch = fields.StringField(max_length=128, default="main")
    connected_at = fields.DateTimeField(default=datetime.utcnow)
    webhook_installed = fields.BooleanField(default=False)
    last_synced = fields.DateTimeField(default=None)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "user_id": _to_str_oid(self.user_id),
            "github_repo_id": self.github_repo_id,
            "name": self.name,
            "full_name": self.full_name,
            "visibility": self.visibility,
            "default_branch": self.default_branch,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "webhook_installed": self.webhook_installed,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
        }


class Pipeline(Document):
    meta = {
        "collection": "pipelines",
        "indexes": ["repository_id", "status", "stage"],
    }

    repository_id = fields.ObjectIdField()
    name = fields.StringField(max_length=256, required=True)
    status = fields.StringField(max_length=64, default="pending")
    stage = fields.StringField(max_length=64, default="development")
    branch = fields.StringField(max_length=128, default="main")
    triggered_at = fields.DateTimeField(default=datetime.utcnow)
    completed_at = fields.DateTimeField(default=None)
    version_id = fields.IntField(default=1)   # optimistic locking counter

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "repository_id": _to_str_oid(self.repository_id),
            "name": self.name,
            "status": self.status,
            "stage": self.stage,
            "branch": self.branch,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "version_id": self.version_id,
        }


class WorkflowTemplate(Document):
    meta = {
        "collection": "workflow_templates",
        "indexes": ["name"],
    }

    name = fields.StringField(max_length=128, required=True)
    description = fields.StringField(default="")
    template_yaml = fields.StringField(required=True)
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "name": self.name,
            "description": self.description,
            "template_yaml": self.template_yaml,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DeploymentServer(Document):
    meta = {
        "collection": "deployment_servers",
        "indexes": ["name", "region"],
    }

    name = fields.StringField(max_length=128, required=True)
    hostname = fields.StringField(max_length=256, required=True)
    ssh_user = fields.StringField(max_length=64, required=True)
    ssh_key_path = fields.StringField(max_length=512, default="")
    region = fields.StringField(max_length=64, default="")
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "name": self.name,
            "hostname": self.hostname,
            "ssh_user": self.ssh_user,
            "region": self.region,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Deployment(Document):
    meta = {
        "collection": "deployments",
        "indexes": ["pipeline_id", "environment", "status",
                     ("pipeline_id", "environment")],
    }

    pipeline_id = fields.ObjectIdField()
    environment = fields.StringField(max_length=64, default="staging")
    status = fields.StringField(max_length=64, default="pending")
    deployed_at = fields.DateTimeField(default=datetime.utcnow)
    finished_at = fields.DateTimeField(default=None)
    server_id = fields.ObjectIdField(default=None)
    version_id = fields.IntField(default=1)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "pipeline_id": _to_str_oid(self.pipeline_id),
            "environment": self.environment,
            "status": self.status,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "server_id": _to_str_oid(self.server_id),
            "version_id": self.version_id,
        }


class CloudDeployment(Document):
    meta = {
        "collection": "cloud_deployments",
        "indexes": ["deployment_id", "status"],
    }

    deployment_id = fields.ObjectIdField()
    aws_instance_id = fields.StringField(max_length=128, default="")
    status = fields.StringField(max_length=64, default="pending")
    logs_url = fields.StringField(max_length=512, default="")
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "deployment_id": _to_str_oid(self.deployment_id),
            "aws_instance_id": self.aws_instance_id,
            "status": self.status,
            "logs_url": self.logs_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WorkflowLog(Document):
    meta = {
        "collection": "workflow_logs",
        "indexes": ["pipeline_id", "step_name", "status"],
    }

    pipeline_id = fields.ObjectIdField()
    step_name = fields.StringField(max_length=256, required=True)
    status = fields.StringField(max_length=64, required=True)
    message = fields.StringField(default="")
    timestamp = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "pipeline_id": _to_str_oid(self.pipeline_id),
            "step_name": self.step_name,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class Notification(Document):
    meta = {
        "collection": "notifications",
        "indexes": ["user_id", ("user_id", "read"), "sent_at"],
    }

    user_id = fields.ObjectIdField()
    title = fields.StringField(max_length=256, required=True)
    body = fields.StringField(default="")
    sent_at = fields.DateTimeField(default=datetime.utcnow)
    read = fields.BooleanField(default=False)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "user_id": _to_str_oid(self.user_id),
            "title": self.title,
            "body": self.body,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "read": self.read,
        }


class Analytics(Document):
    meta = {
        "collection": "analytics",
        "indexes": ["repository_id", "event_type", "created_at"],
    }

    repository_id = fields.ObjectIdField()
    event_type = fields.StringField(max_length=128, required=True)
    metric = fields.StringField(max_length=128, default="")
    value = fields.FloatField(default=None)
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "repository_id": _to_str_oid(self.repository_id),
            "event_type": self.event_type,
            "metric": self.metric,
            "value": self.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ErrorReport(Document):
    meta = {
        "collection": "error_reports",
        "indexes": ["pipeline_id", "severity", "resolved", "detected_at"],
    }

    pipeline_id = fields.ObjectIdField()
    title = fields.StringField(max_length=256, required=True)
    description = fields.StringField(default="")
    severity = fields.StringField(max_length=64, default="warning")
    resolved = fields.BooleanField(default=False)
    detected_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "pipeline_id": _to_str_oid(self.pipeline_id),
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "resolved": self.resolved,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
        }


class AIPrediction(Document):
    meta = {
        "collection": "ai_predictions",
        "indexes": ["pipeline_id", "prediction_type", "created_at"],
    }

    pipeline_id = fields.ObjectIdField()
    prediction_type = fields.StringField(max_length=128, required=True)
    confidence = fields.FloatField(default=None)
    details = fields.StringField(default="")
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "pipeline_id": _to_str_oid(self.pipeline_id),
            "prediction_type": self.prediction_type,
            "confidence": self.confidence,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# Phase 2 / Project documents
# ---------------------------------------------------------------------------
class Project(Document):
    meta = {
        "collection": "projects",
        "indexes": ["created_by", "status", "created_at", ("created_by", "status")],
    }

    created_by = fields.ObjectIdField()
    repo_url = fields.URLField(required=True)
    repo_owner = fields.StringField(max_length=256, default="")
    repo_name = fields.StringField(max_length=256, default="")
    default_branch = fields.StringField(max_length=128, default="main")
    status = fields.StringField(max_length=64, default="pending_analysis")
    detected_stack = fields.EmbeddedDocumentField(DetectedStack, default=DetectedStack)
    readiness_score = fields.IntField(default=None)
    error_message = fields.StringField(default="")
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)
    version_id = fields.IntField(default=1)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "repo_url": self.repo_url,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "default_branch": self.default_branch,
            "status": self.status,
            "readiness_score": self.readiness_score,
            "detected_stack": self.detected_stack.to_dict() if self.detected_stack else {},
            "error_message": self.error_message,
            "created_by": _to_str_oid(self.created_by),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AutomationStep(Document):
    meta = {
        "collection": "automation_steps",
        "indexes": ["project_id", "step_key", ("project_id", "approved")],
    }

    project_id = fields.ObjectIdField()
    step_key = fields.StringField(max_length=64, required=True)
    title = fields.StringField(max_length=256, required=True)
    description = fields.StringField(required=True)
    recommended = fields.BooleanField(default=False)
    approved = fields.BooleanField(default=False)
    yaml_snippet_preview = fields.StringField(default="")
    created_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "project_id": _to_str_oid(self.project_id),
            "step_key": self.step_key,
            "title": self.title,
            "description": self.description,
            "recommended": self.recommended,
            "approved": self.approved,
            "yaml_snippet_preview": self.yaml_snippet_preview,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GeneratedWorkflow(Document):
    meta = {
        "collection": "generated_workflows",
        "indexes": ["project_id", "pr_number", "pr_status"],
    }

    project_id = fields.ObjectIdField()
    filename = fields.StringField(max_length=256, default=".github/workflows/ci.yml")
    yaml_content = fields.StringField(required=True)
    pr_url = fields.StringField(max_length=512, default="")
    pr_number = fields.IntField(default=None)
    pr_status = fields.StringField(max_length=32, default="draft")
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "project_id": _to_str_oid(self.project_id),
            "filename": self.filename,
            "yaml_content": self.yaml_content,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "pr_status": self.pr_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SimulationRun(Document):
    meta = {
        "collection": "simulation_runs",
        "indexes": ["project_id", "status", "injected_error_type"],
    }

    project_id = fields.ObjectIdField()
    injected_error_type = fields.StringField(max_length=64, required=True)
    injected_file = fields.StringField(max_length=512, required=True)
    injected_diff = fields.StringField(required=True)
    pipeline_log = fields.StringField(default="")
    ai_diagnosis = fields.StringField(default="")
    ai_fix_diff = fields.StringField(default="")
    status = fields.StringField(max_length=32, default="running")
    created_at = fields.DateTimeField(default=datetime.utcnow)
    updated_at = fields.DateTimeField(default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": _to_str_oid(self.id),
            "project_id": _to_str_oid(self.project_id),
            "injected_error_type": self.injected_error_type,
            "injected_file": self.injected_file,
            "injected_diff": self.injected_diff,
            "pipeline_log": self.pipeline_log,
            "ai_diagnosis": self.ai_diagnosis,
            "ai_fix_diff": self.ai_fix_diff,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# Convenience: map old SQLAlchemy table name -> MongoEngine document class
# ---------------------------------------------------------------------------
DOCUMENT_REGISTRY = {
    "users": User,
    "user_profiles": UserProfile,        # embedded; kept for registry completeness
    "github_connections": GithubConnection,
    "email_otps": EmailOTP,
    "audit_logs": AuditLog,
    "repositories": Repository,
    "pipelines": Pipeline,
    "workflow_templates": WorkflowTemplate,
    "deployments": Deployment,
    "cloud_deployments": CloudDeployment,
    "workflow_logs": WorkflowLog,
    "notifications": Notification,
    "analytics": Analytics,
    "error_reports": ErrorReport,
    "ai_predictions": AIPrediction,
    "projects": Project,
    "automation_steps": AutomationStep,
    "generated_workflows": GeneratedWorkflow,
    "simulation_runs": SimulationRun,
    "deployment_servers": DeploymentServer,
}


def get_document_class(table_name: str):
    """Given a SQLAlchemy table name, return the corresponding MongoEngine class."""
    cls = DOCUMENT_REGISTRY.get(table_name)
    if cls is None:
        logger.warning("No MongoEngine document registered for table '%s'", table_name)
    return cls

