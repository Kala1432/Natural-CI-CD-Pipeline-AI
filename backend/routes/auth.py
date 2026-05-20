from flask import Blueprint, request, jsonify, current_app, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from backend.models import User
from backend.db import db
import requests

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        name=name,
        role="developer",
    )
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=user.id)
    return jsonify({"access_token": token, "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    user = User.query.filter_by(email=email).first()

    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(identity=user.id)
    return jsonify({"access_token": token, "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}})


@auth_bp.route("/profile", methods=["GET"])
@jwt_required()
def profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"id": user.id, "email": user.email, "name": user.name, "role": user.role})


@auth_bp.route("/github/login")
def github_login():
    client_id = current_app.config["GITHUB_CLIENT_ID"]
    redirect_uri = url_for("auth.github_callback", _external=True)
    return redirect(
        f"https://github.com/login/oauth/authorize?client_id={client_id}&scope=repo,user&redirect_uri={redirect_uri}"
    )


@auth_bp.route("/github/callback")
def github_callback():
    code = request.args.get("code")
    client_id = current_app.config["GITHUB_CLIENT_ID"]
    client_secret = current_app.config["GITHUB_CLIENT_SECRET"]
    token_url = "https://github.com/login/oauth/access_token"
    headers = {"Accept": "application/json"}
    payload = {"client_id": client_id, "client_secret": client_secret, "code": code}
    response = requests.post(token_url, json=payload, headers=headers)
    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        return jsonify({"error": "GitHub OAuth failed"}), 400
    user_resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()
    github_id = str(user_resp.get("id"))
    email = user_resp.get("email") or f"{github_id}@github"
    user = User.query.filter_by(github_id=github_id).first()
    if not user:
        user = User(email=email, github_id=github_id, name=user_resp.get("name"), role="developer")
        db.session.add(user)
    else:
        user.name = user_resp.get("name")
    db.session.commit()
    token = create_access_token(identity=user.id)
    return jsonify({"access_token": token, "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}})
