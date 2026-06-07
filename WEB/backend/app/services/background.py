"""Background task helpers for FastAPI.

Uses FastAPI's built-in BackgroundTasks for lightweight async work.
For heavier workloads, swap the implementations for Celery/RQ workers.

Usage in any endpoint:
    from fastapi import BackgroundTasks
    from app.services.background import enqueue_email, enqueue_audit_log

    @router.post("/example")
    async def example(bg: BackgroundTasks):
        bg.add_task(enqueue_email, "user@example.com", "Subject", "<p>body</p>")
        return {"ok": True}
"""

from app.core.logging import get_logger

logger = get_logger(__name__)


async def enqueue_email(to: str, subject: str, html_body: str) -> None:
    """Send email in background (non-blocking)."""
    from app.services.email import send_email
    await send_email(to, subject, html_body)


async def enqueue_audit_log(event: str, user_id: int | None, details: dict) -> None:
    """Persist an audit event in background."""
    logger.info(
        "audit_event=%s user_id=%s details=%s",
        event,
        user_id,
        details,
    )
