import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


import secrets

class Config:
    ENV = os.environ.get("FLASK_ENV", "development")

    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        if ENV == "production":
            raise ValueError("SECRET_KEY must be set in production")
        SECRET_KEY = os.environ.get("SECRET_KEY_DEV", "dev_secret_" + "a" * 32)

    _db_url = os.environ.get("DATABASE_URL", "sqlite:///hifi_local.db")
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"connect_args": {"check_same_thread": False}}
        if _db_url.startswith("sqlite")
        else {}
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        if ENV == "production":
            raise ValueError("JWT_SECRET_KEY must be set in production")
        JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY_DEV", "dev_jwt_secret_" + "b" * 32)
        
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_COOKIE_SECURE = ENV == "production"
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_SAMESITE = "Lax"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_CSRF_METHOD = "Cookie"

    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
    GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not GITHUB_WEBHOOK_SECRET:
        if ENV == "production":
            raise ValueError("GITHUB_WEBHOOK_SECRET must be set in production")
        GITHUB_WEBHOOK_SECRET = secrets.token_urlsafe(32)

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    BACKEND_URL = os.environ.get("BACKEND_URL", "http://13.51.172.247:5001")

    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 465))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_APP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USERNAME)
    OTP_EXPIRY_MINUTES = int(os.environ.get("OTP_EXPIRY_MINUTES", 10))
    OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("OTP_RESEND_COOLDOWN_SECONDS", 60))
    OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", 5))
    EMAIL_VERIFICATION_REQUIRED = os.environ.get(
        "EMAIL_VERIFICATION_REQUIRED", "true"
    ).lower() in ("1", "true", "yes")
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "false").lower() in (
        "1", "true", "yes"
    )

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    REDIS_CACHE_TTL = int(os.environ.get("REDIS_CACHE_TTL", 300))
    SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "true").lower() in (
        "1", "true", "yes"
    )

    # AWS Configuration
    # AWS_DEPLOYMENT_MODE: "simulation" (default for development/testing) or "real" (for production AWS infrastructure)
    AWS_DEPLOYMENT_MODE = os.environ.get("AWS_DEPLOYMENT_MODE", "simulation").lower()
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", "pipeline-sh-artifacts")
    AWS_EC2_KEY_NAME = os.environ.get("AWS_EC2_KEY_NAME", "pipeline-sh-ec2-key")
    AWS_SSH_USER = os.environ.get("AWS_SSH_USER", "ubuntu")
    AWS_EC2_AMI_ID = os.environ.get("AWS_EC2_AMI_ID", "ami-0c7217cdde317cfec")  # Ubuntu 22.04 LTS
    AWS_EC2_INSTANCE_TYPE = os.environ.get("AWS_EC2_INSTANCE_TYPE", "t3.micro")

    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://13.51.172.247:8080")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    # MongoDB / Atlas configuration (for dual-write migration phase)
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/pipeline_sh")
    MONGODB_DB = os.environ.get("MONGODB_DB", "pipeline_sh")
    # Optional: MongoDB connection pool settings
    MONGODB_MAX_POOL_SIZE = int(os.environ.get("MONGODB_MAX_POOL_SIZE", 50))
    MONGODB_MIN_POOL_SIZE = int(os.environ.get("MONGODB_MIN_POOL_SIZE", 0))
    MONGODB_MAX_IDLE_TIME_MS = int(os.environ.get("MONGODB_MAX_IDLE_TIME_MS", 30000))
    MONGODB_WAIT_QUEUE_TIMEOUT_MS = int(os.environ.get("MONGODB_WAIT_QUEUE_TIMEOUT_MS", 5000))
