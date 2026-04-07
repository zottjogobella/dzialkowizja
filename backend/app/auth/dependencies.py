from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import User

from .session import validate_session


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    dzialkowizja_session: str | None = Cookie(default=None),
) -> User | None:
    """Returns the authenticated user or None."""
    if not dzialkowizja_session:
        return None
    return await validate_session(db, dzialkowizja_session)


async def require_auth(
    user: User | None = Depends(get_current_user),
) -> User:
    """Raises 401 if not authenticated."""
    if user is None:
        raise HTTPException(status_code=401, detail="Nie jesteś zalogowany")
    return user
