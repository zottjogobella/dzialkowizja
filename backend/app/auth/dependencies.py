from __future__ import annotations

from collections.abc import Callable
from typing import Awaitable

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


def require_role(*allowed_roles: str) -> Callable[[User], Awaitable[User]]:
    """Build a dependency that 403s when the user's role is not allowed."""

    async def _dep(user: User = Depends(require_auth)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Brak uprawnień")
        return user

    return _dep


require_admin = require_role("admin", "super_admin")
require_super_admin = require_role("super_admin")
