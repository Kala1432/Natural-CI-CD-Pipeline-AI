import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "pipeline_sh_secret")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pipeline_sh")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt_secret_pipeline_sh")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "pipeline-sh-artifacts")
    AWS_EC2_KEY_NAME = os.environ.get("AWS_EC2_KEY_NAME", "pipeline-sh-ec2-key")
    AWS_SSH_USER = os.environ.get("AWS_SSH_USER", "ubuntu")
    AWS_DEFAULT_OUTPUT = "json"
    GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "secret")
    REDIS_CACHE_TTL = int(os.environ.get("REDIS_CACHE_TTL", 300))
