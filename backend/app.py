from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

from backend.db import db
from backend.config import Config
from backend.routes.auth import auth_bp
from backend.routes.github import github_bp
from backend.routes.pipeline import pipeline_bp
from backend.routes.deploy import deploy_bp
from backend.routes.analytics import analytics_bp
from backend.tasks import configure_scheduler
n

def create_app():
    load_dotenv()
    app = Flask(__name__, static_folder="../frontend/dist", static_url_path="")
    app.config.from_object(Config)

    CORS(app, supports_credentials=True)
    JWTManager(app)
    db.init_app(app)
    Migrate(app, db)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(github_bp, url_prefix="/api/github")
    app.register_blueprint(pipeline_bp, url_prefix="/api/pipelines")
    app.register_blueprint(deploy_bp, url_prefix="/api/deploy")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")

    configure_scheduler(app)

    @app.route("/api/health")
    def health():
        return {"status": "ok", "service": "Pipeline.sh API"}

    @app.route("/<path:path>")
    def frontend_files(path):
        return app.send_static_file(path)

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
