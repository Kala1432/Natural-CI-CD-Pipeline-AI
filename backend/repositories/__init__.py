"""
Repository layer — abstracts MongoEngine document access so route and
service code never touches raw querysets.

Each repository owns a single MongoEngine document class and exposes a
small, intention-revealing API.  All ObjectId<->str conversions are done
inside the repository so callers can stay in string-Id space.
"""

from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from typing import Iterable, Optional, List, Dict, Any

from backend.models_mongo import (
    User,
    UserProfile,
    GithubConnection,
    EmailOTP,
    AuditLog,
    Repository as Repo,
    Pipeline,
    WorkflowTemplate,
    Deployment,
    CloudDeployment,
    WorkflowLog,
    Notification,
    Analytics,
    ErrorReport,
    AIPrediction,
    Project,
    AutomationStep,
    GeneratedWorkflow,
    SimulationRun,
    DeploymentServer,
)


def to_oid(value) -> Optional[ObjectId]:
    """Safely coerce ``str | int | ObjectId`` to an ObjectId, or ``None``."""
    if value is None or value == "":
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        return None


def to_str(value) -> Optional[str]:
    """Safely coerce any identifier to a hex string, or ``None``."""
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return str(value)
    return str(value)


class _BaseRepository:
    """Shared helpers for all repositories."""

    document_class = None  # subclasses set this

    def _to_dict_list(self, docs: Iterable) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in docs] if docs else []

    def get_by_id(self, doc_id):
        return self.document_class.objects(id=to_oid(doc_id)).first()

    def get_by_id_str(self, doc_id) -> Optional[Dict[str, Any]]:
        obj = self.get_by_id(doc_id)
        return obj.to_dict() if obj else None

    def delete_by_id(self, doc_id) -> bool:
        obj = self.get_by_id(doc_id)
        if obj is None:
            return False
        obj.delete()
        return True

    def count(self) -> int:
        return self.document_class.objects.count()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class UserRepository(_BaseRepository):
    document_class = User

    def find_by_email(self, email: str):
        return self.document_class.objects(email=email).first()

    def find_by_google_id(self, google_id: str):
        return self.document_class.objects(google_id=google_id).first()

    def find_by_github_id(self, github_id: str):
        return self.document_class.objects(github_id=github_id).first()

    def create_user(
        self,
        email: str,
        password_hash: str = "",
        name: str = "",
        role: str = "developer",
        email_verified: bool = False,
        is_admin: bool = False,
        avatar_url: str = "",
        google_id: str = "",
        github_id: str = "",
    ) -> User:
        user = User(
            id=ObjectId(),
            email=email,
            password_hash=password_hash,
            name=name,
            role=role,
            email_verified=email_verified,
            is_admin=is_admin,
            avatar_url=avatar_url,
            google_id=google_id,
            github_id=github_id,
            profile=UserProfile(),
        )
        user.save()
        return user

    def update_last_login(self, user_id):
        self.document_class.objects(id=to_oid(user_id)).update(set__updated_at=datetime.utcnow)

    def list_all(self) -> List[Dict[str, Any]]:
        return self._to_dict_list(self.document_class.objects.all())


# ---------------------------------------------------------------------------
# GithubConnection
# ---------------------------------------------------------------------------
class GithubConnectionRepository(_BaseRepository):
    document_class = GithubConnection

    def find_by_user(self, user_id) -> List[GithubConnection]:
        return list(self.document_class.objects(user_id=to_oid(user_id)))

    def find_by_user_and_github_id(self, user_id, github_id: str):
        return self.document_class.objects(
            user_id=to_oid(user_id), github_id=github_id
        ).first()

    def upsert(self, user_id, github_id: str, login: str, access_token: str = ""):
        existing = self.find_by_user_and_github_id(user_id, github_id)
        if existing:
            existing.login = login or existing.login
            if access_token:
                existing.access_token = access_token
            existing.save()
            return existing
        return self.document_class(
            user_id=to_oid(user_id),
            github_id=github_id,
            login=login,
            access_token=access_token,
        ).save()


# ---------------------------------------------------------------------------
# EmailOTP
# ---------------------------------------------------------------------------
class EmailOTPRepository(_BaseRepository):
    document_class = EmailOTP

    def find_by_user(self, user_id) -> List[EmailOTP]:
        return list(self.document_class.objects(user_id=to_oid(user_id)))

    def latest_for(self, user_id, purpose: str):
        return self.document_class.objects(
            user_id=to_oid(user_id), purpose=purpose
        ).order_by("-created_at").first()

    def create_otp(
        self, user_id, purpose: str, code_hash: str, expires_at: datetime
    ) -> EmailOTP:
        return self.document_class(
            user_id=to_oid(user_id),
            purpose=purpose,
            code_hash=code_hash,
            expires_at=expires_at,
        ).save()

    def consume(self, otp) -> None:
        otp.consumed_at = datetime.utcnow()
        otp.save()

    def increment_attempts(self, otp) -> int:
        otp.attempts = (otp.attempts or 0) + 1
        otp.save()
        return otp.attempts

    def purge_expired(self) -> int:
        """Delete all consumed or expired OTPs (used in tests; TTL handles prod)."""
        return self.document_class.objects(
            otp_expires_at__lt=datetime.utcnow()
        ).delete()


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------
class AuditLogRepository(_BaseRepository):
    document_class = AuditLog

    def find_by_user(self, user_id, limit: int = 100) -> List[AuditLog]:
        return list(
            self.document_class.objects(user_id=to_oid(user_id))
            .order_by("-created_at")
            .limit(limit)
        )

    def find_by_action(self, action: str, limit: int = 100) -> List[AuditLog]:
        return list(
            self.document_class.objects(action=action)
            .order_by("-created_at")
            .limit(limit)
        )

    def list_recent(
        self,
        limit: int = 50,
        action: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[AuditLog]:
        q = self.document_class.objects
        if action:
            q = q.filter(action=action)
        if status:
            q = q.filter(status=status)
        return list(q.order_by("-created_at").limit(limit))

    def create(
        self,
        action: str,
        user_id=None,
        resource_type: str = "",
        resource_id: str = "",
        details: Optional[dict] = None,
        status: str = "success",
        ip_address: str = "",
        user_agent: str = "",
    ) -> AuditLog:
        return self.document_class(
            user_id=to_oid(user_id),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
        ).save()


# ---------------------------------------------------------------------------
# Repository (note: model class is named ``Repository`` -> Document registry uses
# 'repositories' to avoid clashing with this class name)
# ---------------------------------------------------------------------------
class RepositoryRepository(_BaseRepository):
    document_class = Repo

    def find_by_user(self, user_id) -> List[Repo]:
        return list(self.document_class.objects(user_id=to_oid(user_id)))

    def find_by_full_name(self, user_id, full_name: str):
        return self.document_class.objects(
            user_id=to_oid(user_id), full_name=full_name
        ).first()

    def find_by_github_id(self, github_repo_id: str):
        return self.document_class.objects(github_repo_id=github_repo_id).first()

    def create(
        self,
        user_id,
        github_repo_id: str,
        name: str,
        full_name: str,
        visibility: str = "public",
        default_branch: str = "main",
    ) -> Repo:
        return self.document_class(
            user_id=to_oid(user_id),
            github_repo_id=github_repo_id,
            name=name,
            full_name=full_name,
            visibility=visibility,
            default_branch=default_branch,
        ).save()

    def mark_synced(self, repo_id) -> None:
        self.document_class.objects(id=to_oid(repo_id)).update(set__last_synced=datetime.utcnow)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
class PipelineRepository(_BaseRepository):
    document_class = Pipeline

    def find_by_repository(self, repository_id) -> List[Pipeline]:
        return list(self.document_class.objects(repository_id=to_oid(repository_id)))

    def find_active(self, repository_id):
        return self.document_class.objects(
            repository_id=to_oid(repository_id), status__nin=["completed", "failed"]
        )

    def create(
        self,
        repository_id,
        name: str,
        status: str = "pending",
        stage: str = "development",
        branch: str = "main",
    ) -> Pipeline:
        return self.document_class(
            repository_id=to_oid(repository_id),
            name=name,
            status=status,
            stage=stage,
            branch=branch,
        ).save()

    def update_status(self, pipeline_id, status: str, completed: bool = False):
        set_updates = {"set__status": status, "inc__version_id": 1}
        if completed:
            set_updates["set__completed_at"] = datetime.utcnow
        self.document_class.objects(id=to_oid(pipeline_id)).update(**set_updates)


# ---------------------------------------------------------------------------
# WorkflowTemplate
# ---------------------------------------------------------------------------
class WorkflowTemplateRepository(_BaseRepository):
    document_class = WorkflowTemplate

    def find_by_name(self, name: str):
        return self.document_class.objects(name=name).first()

    def create(self, name: str, template_yaml: str, description: str = "") -> WorkflowTemplate:
        return self.document_class(
            name=name, description=description, template_yaml=template_yaml
        ).save()


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------
class DeploymentRepository(_BaseRepository):
    document_class = Deployment

    def find_by_pipeline(self, pipeline_id) -> List[Deployment]:
        return list(self.document_class.objects(pipeline_id=to_oid(pipeline_id)))

    def list_recent(self, limit: int = 20) -> List[Deployment]:
        return list(self.document_class.objects.order_by("-deployed_at").limit(limit))

    def count_active(self) -> int:
        return self.document_class.objects(status="running").count()

    def create(
        self,
        pipeline_id,
        environment: str = "staging",
        status: str = "pending",
        server_id=None,
    ) -> Deployment:
        return self.document_class(
            pipeline_id=to_oid(pipeline_id),
            environment=environment,
            status=status,
            server_id=to_oid(server_id),
        ).save()

    def update_status(self, deployment_id, status: str):
        self.document_class.objects(id=to_oid(deployment_id)).update(
            **{"set__status": status, "inc__version_id": 1}
        )


# ---------------------------------------------------------------------------
# CloudDeployment
# ---------------------------------------------------------------------------
class CloudDeploymentRepository(_BaseRepository):
    document_class = CloudDeployment

    def find_by_deployment(self, deployment_id):
        return self.document_class.objects(
            deployment_id=to_oid(deployment_id)
        ).first()

    def create(
        self,
        deployment_id,
        aws_instance_id: str = "",
        status: str = "pending",
        logs_url: str = "",
    ) -> CloudDeployment:
        return self.document_class(
            deployment_id=to_oid(deployment_id),
            aws_instance_id=aws_instance_id,
            status=status,
            logs_url=logs_url,
        ).save()


# ---------------------------------------------------------------------------
# WorkflowLog
# ---------------------------------------------------------------------------
class WorkflowLogRepository(_BaseRepository):
    document_class = WorkflowLog

    def find_by_pipeline(self, pipeline_id) -> List[WorkflowLog]:
        return list(self.document_class.objects(pipeline_id=to_oid(pipeline_id)))

    def create(
        self, pipeline_id, step_name: str, status: str, message: str = ""
    ) -> WorkflowLog:
        return self.document_class(
            pipeline_id=to_oid(pipeline_id),
            step_name=step_name,
            status=status,
            message=message,
        ).save()


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------
class NotificationRepository(_BaseRepository):
    document_class = Notification

    def find_by_user(self, user_id, unread_only: bool = False) -> List[Notification]:
        q = self.document_class.objects(user_id=to_oid(user_id))
        if unread_only:
            q = q.filter(read=False)
        return list(q.order_by("-sent_at"))

    def create(self, user_id, title: str, body: str = "") -> Notification:
        return self.document_class(user_id=to_oid(user_id), title=title, body=body).save()

    def mark_read(self, notification_id) -> None:
                self.document_class.objects(id=to_oid(notification_id)).update(set__read=True)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class AnalyticsRepository(_BaseRepository):
    document_class = Analytics

    def find_by_repository(self, repository_id) -> List[Analytics]:
        return list(self.document_class.objects(repository_id=to_oid(repository_id)))

    def record(
        self,
        repository_id,
        event_type: str,
        metric: str = "",
        value: Optional[float] = None,
    ) -> Analytics:
        return self.document_class(
            repository_id=to_oid(repository_id),
            event_type=event_type,
            metric=metric,
            value=value,
        ).save()


# ---------------------------------------------------------------------------
# ErrorReport
# ---------------------------------------------------------------------------
class ErrorReportRepository(_BaseRepository):
    document_class = ErrorReport

    def find_by_pipeline(self, pipeline_id) -> List[ErrorReport]:
        return list(self.document_class.objects(pipeline_id=to_oid(pipeline_id)))

    def latest_for_pipeline(self, pipeline_id):
        return self.document_class.objects(
            pipeline_id=to_oid(pipeline_id)
        ).order_by("-detected_at").first()

    def create(
        self,
        pipeline_id,
        title: str,
        description: str = "",
        severity: str = "warning",
    ) -> ErrorReport:
        return self.document_class(
            pipeline_id=to_oid(pipeline_id),
            title=title,
            description=description,
            severity=severity,
        ).save()


# ---------------------------------------------------------------------------
# AIPrediction
# ---------------------------------------------------------------------------
class AIPredictionRepository(_BaseRepository):
    document_class = AIPrediction

    def find_by_pipeline(self, pipeline_id) -> List[AIPrediction]:
        return list(self.document_class.objects(pipeline_id=to_oid(pipeline_id)))

    def create(
        self,
        pipeline_id,
        prediction_type: str,
        confidence: Optional[float] = None,
        details: str = "",
    ) -> AIPrediction:
        return self.document_class(
            pipeline_id=to_oid(pipeline_id),
            prediction_type=prediction_type,
            confidence=confidence,
            details=details,
        ).save()


# ---------------------------------------------------------------------------
# DeploymentServer
# ---------------------------------------------------------------------------
class DeploymentServerRepository(_BaseRepository):
    document_class = DeploymentServer

    def find_by_name(self, name: str):
        return self.document_class.objects(name=name).first()

    def create(
        self,
        name: str,
        hostname: str,
        ssh_user: str,
        ssh_key_path: str = "",
        region: str = "",
    ) -> DeploymentServer:
        return self.document_class(
            name=name,
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path,
            region=region,
        ).save()


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class ProjectRepository(_BaseRepository):
    document_class = Project

    def find_by_creator(self, user_id) -> List[Project]:
        return list(self.document_class.objects(created_by=to_oid(user_id)))

    def find_by_id_for_user(self, project_id, user_id):
        return self.document_class.objects(
            id=to_oid(project_id), created_by=to_oid(user_id)
        ).first()

    def find_by_repo(self, repo_owner: str, repo_name: str) -> List[Project]:
        """Find all projects matching the given repo owner and name."""
        return list(self.document_class.objects(
            repo_owner=repo_owner, repo_name=repo_name
        ))

    def create(
        self,
        created_by,
        repo_url: str,
        repo_owner: str = "",
        repo_name: str = "",
        default_branch: str = "main",
    ) -> Project:
        return self.document_class(
            created_by=to_oid(created_by),
            repo_url=repo_url,
            repo_owner=repo_owner,
            repo_name=repo_name,
            default_branch=default_branch,
        ).save()

    def update_status(
        self,
        project_id,
        status: str,
        detected_stack: Optional[Dict[str, Any]] = None,
        readiness_score: Optional[int] = None,
        error_message: str = "",
    ):
        from backend.models_mongo import DetectedStack
        # Build set__ and inc__ prefixed kwargs for MongoEngine update
        set_updates = {"set__status": status, "inc__version_id": 1}
        if detected_stack is not None:
            set_updates["set__detected_stack"] = DetectedStack(
                language=detected_stack.get("language", ""),
                framework=detected_stack.get("framework", ""),
                package_manager=detected_stack.get("package_manager", ""),
                has_dockerfile=detected_stack.get("has_dockerfile", False),
                has_tests=detected_stack.get("has_tests", False),
            )
        if readiness_score is not None:
            set_updates["set__readiness_score"] = readiness_score
        if error_message:
            set_updates["set__error_message"] = error_message
        self.document_class.objects(id=to_oid(project_id)).update(**set_updates)

    def list_all(self) -> List[Dict[str, Any]]:
        return self._to_dict_list(self.document_class.objects.all())


# ---------------------------------------------------------------------------
# AutomationStep
# ---------------------------------------------------------------------------
class AutomationStepRepository(_BaseRepository):
    document_class = AutomationStep

    def find_by_project(self, project_id) -> List[AutomationStep]:
        return list(self.document_class.objects(project_id=to_oid(project_id)))

    def create(
        self,
        project_id,
        step_key: str,
        title: str,
        description: str,
        recommended: bool = False,
        yaml_snippet_preview: str = "",
    ) -> AutomationStep:
        return self.document_class(
            project_id=to_oid(project_id),
            step_key=step_key,
            title=title,
            description=description,
            recommended=recommended,
            yaml_snippet_preview=yaml_snippet_preview,
        ).save()

    def approve(self, step_id) -> None:
                self.document_class.objects(id=to_oid(step_id)).update(set__approved=True)


# ---------------------------------------------------------------------------
# GeneratedWorkflow
# ---------------------------------------------------------------------------
class GeneratedWorkflowRepository(_BaseRepository):
    document_class = GeneratedWorkflow

    def find_by_project(self, project_id) -> List[GeneratedWorkflow]:
        return list(self.document_class.objects(project_id=to_oid(project_id)))

    def latest_for_project(self, project_id):
        return self.document_class.objects(
            project_id=to_oid(project_id)
        ).order_by("-created_at").first()

    def create(
        self,
        project_id,
        yaml_content: str,
        filename: str = ".github/workflows/ci.yml",
    ) -> GeneratedWorkflow:
        return self.document_class(
            project_id=to_oid(project_id),
            yaml_content=yaml_content,
            filename=filename,
        ).save()

    def update_pr(
        self,
        workflow_id,
        pr_url: str,
        pr_number: int,
        pr_status: str = "open",
    ) -> None:
                self.document_class.objects(id=to_oid(workflow_id)).update(**{"set__pr_url": pr_url, "set__pr_number": pr_number, "set__pr_status": pr_status})


# ---------------------------------------------------------------------------
# SimulationRun
# ---------------------------------------------------------------------------
class SimulationRunRepository(_BaseRepository):
    document_class = SimulationRun

    def find_by_project(self, project_id) -> List[SimulationRun]:
        return list(self.document_class.objects(project_id=to_oid(project_id)))

    def create(
        self,
        project_id,
        injected_error_type: str,
        injected_file: str,
        injected_diff: str,
    ) -> SimulationRun:
        return self.document_class(
            project_id=to_oid(project_id),
            injected_error_type=injected_error_type,
            injected_file=injected_file,
            injected_diff=injected_diff,
        ).save()

    def update_result(
        self,
        run_id,
        pipeline_log: str = "",
        ai_diagnosis: str = "",
        ai_fix_diff: str = "",
        status: str = "running",
    ) -> None:
        updates = {"set__status": status}
        if pipeline_log:
            updates["set__pipeline_log"] = pipeline_log
        if ai_diagnosis:
            updates["set__ai_diagnosis"] = ai_diagnosis
        if ai_fix_diff:
            updates["set__ai_fix_diff"] = ai_fix_diff
        self.document_class.objects(id=to_oid(run_id)).update(**updates)


__all__ = [
    "UserRepository",
    "GithubConnectionRepository",
    "EmailOTPRepository",
    "AuditLogRepository",
    "RepositoryRepository",
    "PipelineRepository",
    "WorkflowTemplateRepository",
    "DeploymentRepository",
    "CloudDeploymentRepository",
    "WorkflowLogRepository",
    "NotificationRepository",
    "AnalyticsRepository",
    "ErrorReportRepository",
    "AIPredictionRepository",
    "DeploymentServerRepository",
    "ProjectRepository",
    "AutomationStepRepository",
    "GeneratedWorkflowRepository",
    "SimulationRunRepository",
    "to_oid",
    "to_str",
]
