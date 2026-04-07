from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Session, User


def _sign_session_id(session_id: str) -> str:
    """HMAC-SHA256 sign the session ID."""
    sig = hmac.new(settings.app_secret_key.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return f"{session_id}.{sig}"


def _verify_signed_session(signed: str) -> str | None:
    """Verify signature and return session ID, or None if invalid."""
    parts = signed.split(".", 1)
    if len(parts) != 2:
        return None
    session_id, sig = parts
    expected = hmac.new(settings.app_secret_key.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return session_id


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """Create a new session. Returns (signed_session_cookie, csrf_token)."""
    csrf_token = secrets.token_urlsafe(32)
    session = Session(
        user_id=user_id,
        csrf_token=csrf_token,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.session_max_age_seconds),
    )
    db.add(session)
    await db.commit()

    signed = _sign_session_id(str(session.id))
    return signed, csrf_token


async def validate_session(db: AsyncSession, signed_cookie: str) -> User | None:
    """Validate session cookie and return the user, or None."""
    session_id = _verify_signed_session(signed_cookie)
    if session_id is None:
        return None

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return None

    result = await db.execute(
        select(Session).where(
            Session.id == sid,
            Session.expires_at > datetime.now(timezone.utc),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None

    # Load user
    result = await db.execute(select(User).where(User.id == session.user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    # Slide session activity (debounced: only if >5 min since last update)
    now = datetime.now(timezone.utc)
    if (now - session.last_active_at).total_seconds() > 300:
        session.last_active_at = now
        await db.commit()

    return user


async def destroy_session(db: AsyncSession, signed_cookie: str) -> None:
    """Delete session from DB."""
    session_id = _verify_signed_session(signed_cookie)
    if session_id is None:
        return

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return

    result = await db.execute(select(Session).where(Session.id == sid))
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        await db.commit()
