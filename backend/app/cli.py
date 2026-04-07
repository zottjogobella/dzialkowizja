"""CLI for managing users. Run from backend/ directory.

Usage:
    python -m app.cli create-user --email admin@example.com --name "Admin" --password "SecurePass1"
    python -m app.cli list-users
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.password import hash_password, validate_password
from app.config import settings
from app.db.models import User


async def _get_session() -> AsyncSession:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory()


async def create_user(email: str, display_name: str, password: str) -> None:
    errors = validate_password(password)
    if errors:
        print("Hasło nie spełnia wymagań:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    async with await _get_session() as db:
        existing = await db.execute(select(User).where(User.email == email.lower()))
        if existing.scalar_one_or_none():
            print(f"Użytkownik z emailem {email} już istnieje")
            sys.exit(1)

        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            display_name=display_name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Utworzono użytkownika: {user.email} (id: {user.id})")


async def list_users() -> None:
    async with await _get_session() as db:
        result = await db.execute(select(User).order_by(User.created_at))
        users = result.scalars().all()
        if not users:
            print("Brak użytkowników")
            return
        for u in users:
            status = "aktywny" if u.is_active else "nieaktywny"
            print(f"  {u.email} | {u.display_name} | {status} | {u.id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dzialkowizja CLI")
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create-user", help="Utwórz nowego użytkownika")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--password", required=True)

    sub.add_parser("list-users", help="Lista użytkowników")

    args = parser.parse_args()

    if args.command == "create-user":
        asyncio.run(create_user(args.email, args.name, args.password))
    elif args.command == "list-users":
        asyncio.run(list_users())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
