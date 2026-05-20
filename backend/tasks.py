from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app
from backend.services.github_service import GitHubService


def sync_repositories():
    current_app.logger.info("Running scheduled repository sync")
    # Placeholder for periodic polling and status refresh.


def configure_scheduler(app):
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(func=sync_repositories, trigger="interval", minutes=10)
    scheduler.start()
    app.logger.info("Scheduler configured for Pipeline.sh")
