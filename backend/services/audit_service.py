import logging
from flask import has_request_context, request

from backend.repositories import AuditLogRepository

logger = logging.getLogger(__name__)


def log_audit_event(
    action: str,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | str | None = None,
    status: str = "success",
):
    """Log an audit event into the database with contextual client metadata."""
    try:
        ip_address = None
        user_agent = None
        if has_request_context():
            ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()
            user_agent = request.headers.get("User-Agent", "")[:500]

        repo = AuditLogRepository()
        entry = repo.create(
            action=action,
            user_id=user_id,
            resource_type=resource_type or "",
            resource_id=str(resource_id) if resource_id is not None else "",
            details=details if isinstance(details, dict) else (
                {"value": str(details)} if details is not None else {}
            ),
            status=status,
            ip_address=ip_address or "",
            user_agent=user_agent or "",
        )
        return entry
    except Exception as exc:
        logger.warning("Failed to record audit log event %s: %s", action, exc)
        return None