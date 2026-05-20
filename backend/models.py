from datetime import datetime
from backend.db import db


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    github_id = db.Column(db.String(64), unique=True, nullable=True)
    role = db.Column(db.String(32), default="developer")
    name = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Repository(db.Model):
    __tablename__ = "repositories"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    github_repo_id = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(256), nullable=False)
    visibility = db.Column(db.String(32), default="public")
    default_branch = db.Column(db.String(128), nullable=False, default="main")
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)
    webhook_installed = db.Column(db.Boolean, default=False)
    last_synced = db.Column(db.DateTime, nullable=True)
    user = db.relationship("User", backref="repositories")


class Pipeline(db.Model):
    __tablename__ = "pipelines"
    id = db.Column(db.Integer, primary_key=True)
    repository_id = db.Column(db.Integer, db.ForeignKey("repositories.id"), nullable=False)
    name = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(64), nullable=False, default="pending")
    stage = db.Column(db.String(64), default="development")
    branch = db.Column(db.String(128), default="main")
    triggered_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    repository = db.relationship("Repository", backref="pipelines")


class WorkflowTemplate(db.Model):
    __tablename__ = "workflow_templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=True)
    template_yaml = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Deployment(db.Model):
    __tablename__ = "deployments"
    id = db.Column(db.Integer, primary_key=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey("pipelines.id"), nullable=False)
    environment = db.Column(db.String(64), default="staging")
    status = db.Column(db.String(64), default="pending")
    deployed_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    server_id = db.Column(db.Integer, db.ForeignKey("deployment_servers.id"), nullable=True)
    pipeline = db.relationship("Pipeline", backref="deployments")
    server = db.relationship("DeploymentServer", backref="deployments")


class WorkflowLog(db.Model):
    __tablename__ = "workflow_logs"
    id = db.Column(db.Integer, primary_key=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey("pipelines.id"), nullable=False)
    step_name = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(64), nullable=False)
    message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    pipeline = db.relationship("Pipeline", backref="workflow_logs")


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    body = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    user = db.relationship("User", backref="notifications")


class Analytics(db.Model):
    __tablename__ = "analytics"
    id = db.Column(db.Integer, primary_key=True)
    repository_id = db.Column(db.Integer, db.ForeignKey("repositories.id"), nullable=False)
    event_type = db.Column(db.String(128), nullable=False)
    metric = db.Column(db.String(128), nullable=True)
    value = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    repository = db.relationship("Repository", backref="analytics")


class ErrorReport(db.Model):
    __tablename__ = "error_reports"
    id = db.Column(db.Integer, primary_key=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey("pipelines.id"), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(64), default="warning")
    resolved = db.Column(db.Boolean, default=False)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    pipeline = db.relationship("Pipeline", backref="error_reports")


class AIPrediction(db.Model):
    __tablename__ = "ai_predictions"
    id = db.Column(db.Integer, primary_key=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey("pipelines.id"), nullable=False)
    prediction_type = db.Column(db.String(128), nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pipeline = db.relationship("Pipeline", backref="ai_predictions")


class CloudDeployment(db.Model):
    __tablename__ = "cloud_deployments"
    id = db.Column(db.Integer, primary_key=True)
    deployment_id = db.Column(db.Integer, db.ForeignKey("deployments.id"), nullable=False)
    aws_instance_id = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(64), default="pending")
    logs_url = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deployment = db.relationship("Deployment", backref="cloud_deployments")


class DeploymentServer(db.Model):
    __tablename__ = "deployment_servers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    hostname = db.Column(db.String(256), nullable=False)
    ssh_user = db.Column(db.String(64), nullable=False)
    ssh_key_path = db.Column(db.String(512), nullable=True)
    region = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
