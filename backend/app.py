import logging
import os
import sys
from datetime import datetime, timezone

# Ensure project root is in sys.path when running app directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from backend.config import Config
from backend.db import db
from backend.routes.analytics import analytics_bp
from backend.routes.auth import auth_bp
from backend.routes.deploy import deploy_bp
from backend.routes.github import github_bp
from backend.routes.pipeline import pipeline_bp
from backend.routes.projects import projects_bp
from backend.routes.workflow import workflow_bp
from backend.tasks import configure_scheduler


def create_app(test_config: dict = None):
    load_dotenv()
    app = Flask(__name__, static_folder="../frontend/dist", static_url_path="")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config.get("TESTING") and (
        not test_config or "EMAIL_VERIFICATION_REQUIRED" not in test_config
    ):
        app.config["EMAIL_VERIFICATION_REQUIRED"] = False

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

    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({"error": e.description}), e.code
        app.logger.exception("Unhandled exception on request: %s", e)
        return jsonify({"error": str(e) if app.debug else "Internal server error"}), 500
    db.init_app(app)
    Migrate(app, db)

    with app.app_context():
        db.create_all()

    blueprints = [
        (auth_bp, "/api/auth"),
        (github_bp, "/api/github"),
        (pipeline_bp, "/api/pipelines"),
        (deploy_bp, "/api/deploy"),
        (analytics_bp, "/api/analytics"),
        (workflow_bp, "/api/workflow"),
        (projects_bp, "/api/projects"),
    ]
    for blueprint, prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=prefix)

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
                db.engine.connect().close()
        except Exception as exc:
            db_status, db_error = "unavailable", str(exc)

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
