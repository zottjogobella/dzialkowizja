"""Audit trail of data-access actions.

Used by data routers to log who accessed what, from which IP, and when.
Distinct from ``search_history`` — that table powers the user-facing
sidebar of recent searches and is shaped around that UI. ActivityLog is
the operator-facing audit trail with IP and per-org filtering.
"""

from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActivityLog, User

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


async def record(
    db: AsyncSession,
    user: User,
    *,
    action_type: str,
    request: Request,
    target_id: str | None = None,
    query_text: str | None = None,
) -> None:
    """Append a single audit row. Swallows errors — auditing must never break a request."""
    try:
        entry = ActivityLog(
            user_id=user.id,
            organization_id=user.organization_id,
            action_type=action_type,
            target_id=target_id,
            query_text=query_text,
            ip_address=_client_ip(request),
            user_agent=(request.headers.get("User-Agent") or "")[:512] or None,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        logger.exception("Failed to record activity action=%s target=%s", action_type, target_id)
        await db.rollback()
