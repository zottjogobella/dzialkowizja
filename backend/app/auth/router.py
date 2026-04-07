from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.engine import get_db
from app.db.models import User

from .dependencies import require_auth
from .password import hash_password, verify_password_timing_safe
from .schemas import LoginRequest, RegisterRequest, UserResponse
from .session import create_session, destroy_session

router = APIRouter()


def _set_cookies(response: Response, signed_session: str, csrf_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=signed_session,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_secure_cookie,
        path="/",
    )
    response.set_cookie(
        key="dzialkowizja_csrf",
        value=csrf_token,
        max_age=settings.session_max_age_seconds,
        httponly=False,  # JS needs to read this
        samesite="strict",
        secure=settings.session_secure_cookie,
        path="/",
    )


@router.post("/register", response_model=UserResponse)
async def register(body: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    # Check if email already taken
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ten email jest już zarejestrowany")

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Auto-login after registration
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (request.client.host if request.client else None)
    signed, csrf = await create_session(db, user.id, ip, request.headers.get("User-Agent"))
    _set_cookies(response, signed, csrf)

    return UserResponse(id=str(user.id), email=user.email, display_name=user.display_name, is_active=user.is_active)


@router.post("/login", response_model=UserResponse)
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    # Timing-safe: always run bcrypt even if user not found
    password_hash = user.password_hash if user else None
    if not verify_password_timing_safe(body.password, password_hash):
        raise HTTPException(status_code=401, detail="Nieprawidłowy email lub hasło")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Konto jest nieaktywne")

    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (request.client.host if request.client else None)
    signed, csrf = await create_session(db, user.id, ip, request.headers.get("User-Agent"))
    _set_cookies(response, signed, csrf)

    return UserResponse(id=str(user.id), email=user.email, display_name=user.display_name, is_active=user.is_active)


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_auth),
):
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        await destroy_session(db, cookie)

    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie("dzialkowizja_csrf", path="/")
    return {"detail": "Wylogowano"}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(require_auth)):
    return UserResponse(id=str(user.id), email=user.email, display_name=user.display_name, is_active=user.is_active)
