import logging
import os
import sys
from datetime import datetime, timezone

# Ensure project root is in sys.path when running app directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
import mongoengine
import mongomock

from backend.config import Config
from backend.routes.analytics import analytics_bp
from backend.routes.auth import auth_bp
from backend.routes.deploy import deploy_bp
from backend.routes.github import github_bp
from backend.routes.pipeline import pipeline_bp
from backend.routes.projects import projects_bp
from backend.routes.workflow import workflow_bp
from backend.routes.simulations import simulations_bp
from backend.routes.admin import admin_bp
from backend.tasks import configure_scheduler


def create_app(test_config: dict = None):
    load_dotenv()
    app = Flask(__name__, static_folder="../frontend/dist", static_url_path="/assets")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config.get("TESTING") and (
        not test_config or "EMAIL_VERIFICATION_REQUIRED" not in test_config
    ):
        app.config["EMAIL_VERIFICATION_REQUIRED"] = False
    if app.config.get("TESTING") and (
        not test_config or "JWT_COOKIE_CSRF_PROTECT" not in test_config
    ):
        app.config["JWT_COOKIE_CSRF_PROTECT"] = False

    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    app.logger.setLevel(log_level)

    CORS(app, supports_credentials=True, origins=[
        r"http://localhost:\d+",
        r"http://127\.0\.0\.1:\d+",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:5000",
        "http://localhost:5000",
    ])
    JWTManager(app)

    # Initialize MongoEngine with mongomock for testing / MongoDB Atlas for production
    mongo_uri = app.config.get("MONGODB_URI", "mongodb://localhost:27017/pipeline_sh")
    mongo_db = app.config.get("MONGODB_DB", "pipeline_sh")
    try:
        # Disconnect any existing connection
        mongoengine.disconnect("default")

        # Check if we're in testing mode - if so, use mongomock
        if app.config.get("TESTING"):
            mongoengine.connect(
                db=mongo_db,
                host="mongodb://localhost:27017/test_db",
                mongo_client_class=mongomock.MongoClient,
                alias="default",
            )
            app.logger.info(f"Connected to MongoDB (mongomock): localhost:27017/{mongo_db}")
        else:
            # For production/development, use real MongoDB
            mongoengine.connect(
                db=mongo_db,
                host=mongo_uri,
                alias="default",
            )
            app.logger.info(f"Connected to MongoDB: {mongo_uri}/{mongo_db}")
    except Exception as e:
        app.logger.warning(f"Could not connect to MongoDB: {e}")

    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({"error": e.description}), e.code
        app.logger.exception("Unhandled exception on request: %s", e)
        return jsonify({"error": str(e) if app.debug else "Internal server error"}), 500

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(projects_bp, url_prefix="/api/projects")
    app.register_blueprint(github_bp, url_prefix="/api/github")
    app.register_blueprint(pipeline_bp, url_prefix="/api/pipelines")
    app.register_blueprint(workflow_bp, url_prefix="/api/workflow")
    app.register_blueprint(simulations_bp, url_prefix="/api")
    app.register_blueprint(deploy_bp, url_prefix="/api/deploy")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    if app.config.get("SCHEDULER_ENABLED") and not app.extensions.get(
        "scheduler_configured"
    ):
        configure_scheduler(app)
        app.extensions["scheduler_configured"] = True

    @app.route("/api/health")
    def health():
        db_status, db_error = "ok", None
        try:
            with app.app_context():
                # Ping MongoDB via MongoEngine
                from mongoengine.connection import get_db
                get_db()
        except Exception as exc:
            db_status, db_error = "degraded", str(exc)

        redis_status, redis_error = "ok", None
        try:
            from redis import Redis
            Redis.from_url(app.config["REDIS_URL"], decode_responses=True).ping()
        except Exception as exc:
            redis_status, redis_error = "unavailable", str(exc)

        overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
        return jsonify({
            "status": overall,
            "service": "HiFi API",
            "version": "1.0.0",
            "database": {"status": db_status, "error": db_error},
            "redis": {"status": redis_status, "error": redis_error},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @app.route("/favicon.svg")
    def favicon():
        return send_from_directory(app.static_folder, "favicon.svg")

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path):
        # Let API routes 404 normally
        if path.startswith("api/"):
            return jsonify({"error": "Not found"}), 404
        # For all SPA routes, always serve index.html
        import os as _os
        index = _os.path.join(app.static_folder, "index.html")
        if _os.path.exists(index):
            return app.send_static_file("index.html")
        return jsonify({"error": "Frontend not built. Run: cd frontend && npm run build"}), 503

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
