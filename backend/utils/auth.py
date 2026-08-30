from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.repositories import UserRepository
from backend.services.audit_service import log_audit_event


def get_current_authenticated_user() -> dict | None:
    """Retrieve the currently authenticated user dict from the JWT identity via MongoDB."""
    try:
        identity = get_jwt_identity()
        if not identity:
            return None
        user_repo = UserRepository()
        return user_repo.get_by_id_str(identity)
    except Exception:
        return None


def role_required(*allowed_roles):
    """Decorator to enforce role-based access control (RBAC)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = get_current_authenticated_user()
            if not user:
                return jsonify({"error": "User not found or unauthenticated"}), 401

            user_role = (user.get("role") or "").lower()
            allowed = [r.lower() for r in allowed_roles]

            if user_role not in allowed and not (user.get("is_admin") and "admin" in allowed):
                log_audit_event(
                    action="rbac.access_denied",
                    user_id=user.get("id"),
                    details={"required_roles": allowed_roles, "user_role": user.get("role")},
                    status="denied",
                )
                return jsonify({
                    "error": f"Forbidden: Insufficient privileges. Required role: {', '.join(allowed_roles)}"
                }), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required():
    """Decorator requiring administrative privileges (role == 'admin' or is_admin == True)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = get_current_authenticated_user()
            if not user:
                return jsonify({"error": "User not found or unauthenticated"}), 401

            if not (user.get("is_admin") or (user.get("role") and user.get("role").lower() == "admin")):
                log_audit_event(
                    action="admin.access_denied",
                    user_id=user.get("id"),
                    status="denied",
                )
                return jsonify({"error": "Forbidden: Administrative access required"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
