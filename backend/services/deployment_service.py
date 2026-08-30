import os
import time
import uuid
import random
import logging
from datetime import datetime

from backend.celery_app import celery_app
from backend.repositories import (
    ProjectRepository,
    DeploymentRepository,
    CloudDeploymentRepository,
    ErrorReportRepository,
    PipelineRepository,
)
from flask import current_app

logger = logging.getLogger(__name__)


def _get_app():
    """Helper to get Flask app context for Celery tasks"""
    from backend.app import create_app
    return create_app()


def _provision_real_aws_ec2(app, project, deployment_id, environment: str) -> dict:
    """
    Provisions a real AWS EC2 instance using boto3.
    Requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION to be set in production.
    """
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError

    region = app.config.get("AWS_REGION", "us-east-1")
    ami_id = app.config.get("AWS_EC2_AMI_ID", "ami-0c7217cdde317cfec")
    instance_type = app.config.get("AWS_EC2_INSTANCE_TYPE", "t3.micro")
    key_name = app.config.get("AWS_EC2_KEY_NAME", "pipeline-sh-ec2-key")
    s3_bucket = app.config.get("AWS_S3_BUCKET", "pipeline-sh-artifacts")

    logger.info("Initializing real AWS EC2 client for deployment %s in region %s", deployment_id, region)
    ec2_client = boto3.client("ec2", region_name=region)

    user_data_script = f"""#!/bin/bash
    echo "Deploying {project.repo_name} (Environment: {environment})" > /var/log/pipeline-deploy.log
    apt-get update -y && apt-get install -y docker.io
    systemctl start docker && systemctl enable docker
    """
    response = ec2_client.run_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        KeyName=key_name,
        MinCount=1,
        MaxCount=1,
        UserData=user_data_script,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": f"pipeline-{project.repo_name}-{environment}"},
                    {"Key": "DeploymentId", "Value": str(deployment_id)},
                    {"Key": "Environment", "Value": environment},
                ],
            }
        ],
    )
    instance_id = response["Instances"][0]["InstanceId"]
    logs_url = f"s3://{s3_bucket}/{instance_id}/deploy.log"
    return {"instance_id": instance_id, "logs_url": logs_url}


@celery_app.task(name="backend.services.deployment_service.run_deployment")
def run_deployment(project_id: str, environment: str = "staging"):
    """
    Executes project deployment.
    Behavior is governed by app.config['AWS_DEPLOYMENT_MODE']:
      - 'real': Provisions real AWS EC2 instances via boto3 API.
      - 'simulation': Simulates EC2 instance creation and provisioning delay.
    """
    app = _get_app()
    with app.app_context():
        project_repo = ProjectRepository()
        project = project_repo.get_by_id(project_id)
        if not project:
            return {"error": "Project not found"}

        deploy_repo = DeploymentRepository()
        cloud_repo = CloudDeploymentRepository()
        err_repo = ErrorReportRepository()
        pipeline_repo = PipelineRepository()

        # 1. Create a Pipeline for this deployment (deployments link to pipelines, not projects)
        pipeline = pipeline_repo.create(
            repository_id=project.repo_owner,  # not a real repository; just a logical reference
            name=f"Deploy-{environment}-{datetime.utcnow().isoformat()}",
            status="running",
            stage=environment,
            branch=project.default_branch or "main",
        )

        # 2. Create Deployment record
        deployment = deploy_repo.create(
            pipeline_id=str(pipeline.id),
            environment=environment,
            status="provisioning",
        )

        deployment_id = str(deployment.id)
        mode = app.config.get("AWS_DEPLOYMENT_MODE", "simulation").lower()
        logger.info(f"Deployment {deployment_id} started for project {project_id} (Mode: {mode})")

        instance_id = None
        logs_url = None

        if mode == "real":
            try:
                real_res = _provision_real_aws_ec2(app, project, deployment_id, environment)
                instance_id = real_res["instance_id"]
                logs_url = real_res["logs_url"]
                logger.info(f"Successfully provisioned real EC2 instance {instance_id}")
            except Exception as exc:
                logger.exception("Real AWS provisioning failed; recording incident: %s", exc)
                deploy_repo.update_status(deployment_id, "failed")
                err_repo.create(
                    pipeline_id=str(pipeline.id),
                    title=f"AWS Provisioning Failed ({environment})",
                    description=f"Could not provision EC2 instance: {str(exc)}",
                    severity="critical"
                )
                return {"error": str(exc), "deployment_id": deployment_id}
        else:
            # Simulation Mode: Provision mock EC2 instance
            time.sleep(1)
            instance_id = f"i-mock-{uuid.uuid4().hex[:8]}"
            logs_url = f"s3://pipeline-logs/{instance_id}/deploy.log"

        # 2. Record CloudDeployment
        cloud_repo.create(
            deployment_id=deployment_id,
            aws_instance_id=instance_id,
            status="running",
            logs_url=logs_url
        )

        deploy_repo.update_status(deployment_id, "running")
        logger.info(f"Deployment {deployment_id} is running on {instance_id}")

        # Kick off background monitor
        monitor_deployment.delay(deployment_id)

        return {"deployment_id": deployment_id, "instance_id": instance_id, "mode": mode}


@celery_app.task(name="backend.services.deployment_service.monitor_deployment")
def monitor_deployment(deployment_id: str, checks: int = 10):
    """
    Monitors deployment health checks.
    In simulation mode, randomly injects anomalies to demonstrate automated incident response and rollbacks.
    """
    app = _get_app()
    with app.app_context():
        deploy_repo = DeploymentRepository()
        err_repo = ErrorReportRepository()
        cloud_repo = CloudDeploymentRepository()

        deployment = deploy_repo.get_by_id(deployment_id)
        if not deployment or deployment.status != "running":
            return

        logger.info(f"Started monitoring deployment {deployment_id}")

        for i in range(checks):
            time.sleep(2)

            deployment = deploy_repo.get_by_id(deployment_id)
            if not deployment or deployment.status != "running":
                break

            cpu_usage = random.randint(10, 100)
            mem_usage = random.randint(40, 95)

            is_anomaly = cpu_usage > 95 or mem_usage > 90

            if is_anomaly or random.random() < 0.05:
                reason = "Anomaly Detected: Resource Spikes" if is_anomaly else "Health Check Failed"
                logger.error(f"{reason} for deployment {deployment_id}! CPU: {cpu_usage}%, Mem: {mem_usage}%")

                deploy_repo.update_status(deployment_id, "failed")

                cloud = cloud_repo.find_by_deployment(deployment_id)
                instance_id = cloud.aws_instance_id if cloud else "Unknown"
                incident = err_repo.create(
                    pipeline_id=str(deployment.pipeline_id),
                    title=f"Deployment Incident ({deployment.environment}): {reason}",
                    description=(
                        f"EC2 Instance failed monitoring criteria. CPU: {cpu_usage}%, "
                        f"Memory: {mem_usage}%. Target instance: {instance_id}."
                    ),
                    severity="critical"
                )

                time.sleep(1)
                deploy_repo.update_status(deployment_id, "rolled_back")
                logger.info(f"Deployment {deployment_id} rolled back automatically.")
                return {"status": "rolled_back", "incident_id": str(incident.id), "anomaly": is_anomaly}

        if deployment.status == "running":
            deploy_repo.update_status(deployment_id, "success")
            logger.info(f"Deployment {deployment_id} finished successfully.")
            return {"status": "success"}
