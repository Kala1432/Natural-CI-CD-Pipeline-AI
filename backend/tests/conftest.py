"""
Shared pytest fixtures for the CI/CD Pipeline test suite.

These fixtures configure a Flask app with MongoEngine wired to mongomock,
so tests can run without a real MongoDB instance.  They replace the
previous SQLAlchemy fixtures that used SQLite in-memory.
"""

import pytest
from bson import ObjectId
from passlib.hash import argon2

from backend.app import create_app
from backend.models_mongo import User, UserProfile


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "JWT_SECRET_KEY": "test-jwt-secret-at-least-32-bytes-long",
        "SECRET_KEY": "test-app-secret-at-least-32-bytes-long",
        "EMAIL_VERIFICATION_REQUIRED": False,
        "MAIL_SUPPRESS_SEND": True,
        "MONGODB_URI": "mongomock://localhost",
    })
    with application.app_context():
        # Drop all collections from previous tests
        for collection in User._get_collection().database.list_collection_names():
            User._get_collection().database.drop_collection(collection)
        yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_user(app):
    """Create an admin user in the test database."""
    with app.app_context():
        user = User(
            id=ObjectId(),
            email="admin@example.com",
            password_hash=argon2.hash("adminpassword123"),
            name="Admin User",
            role="admin",
            is_admin=True,
            email_verified=True,
            profile=UserProfile(),
        )
        user.save()
        return user


@pytest.fixture()
def developer_user(app):
    """Create a regular developer user in the test database."""
    with app.app_context():
        user = User(
            id=ObjectId(),
            email="dev@example.com",
            password_hash=argon2.hash("devpassword123"),
            name="Dev User",
            role="developer",
            is_admin=False,
            email_verified=True,
            profile=UserProfile(),
        )
        user.save()
        return user
