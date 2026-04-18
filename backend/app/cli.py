"""CLI for managing users and organizations. Run from backend/ directory.

Usage:
    python -m app.cli create-user --email user@example.com --name "User" --password "Pw1!" \
        --role user --organization default
    python -m app.cli create-super-admin --email super@example.com --name "Super" --password "Pw1!"
    python -m app.cli list-users
    python -m app.cli create-organization --name "Acme" --slug acme
    python -m app.cli list-organizations
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.password import hash_password, validate_password
from app.config import settings
from app.db.models import Organization, User


async def _get_session() -> AsyncSession:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory()


async def _resolve_org(db: AsyncSession, slug: str | None) -> Organization | None:
    if not slug:
        return None
    org = (
        await db.execute(select(Organization).where(Organization.slug == slug.lower()))
    ).scalar_one_or_none()
    if org is None:
        print(f"Organizacja o slug '{slug}' nie istnieje")
        sys.exit(1)
    return org


async def create_user(
    email: str, display_name: str, password: str, role: str, organization_slug: str | None
) -> None:
    if role not in {"super_admin", "admin", "user"}:
        print("Niepoprawna rola — użyj: super_admin | admin | user")
        sys.exit(1)
    errors = validate_password(password)
    if errors:
        print("Hasło nie spełnia wymagań:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    if role != "super_admin" and not organization_slug:
        print("Rola admin/user wymaga --organization <slug>")
        sys.exit(1)

    async with await _get_session() as db:
        existing = await db.execute(select(User).where(User.email == email.lower()))
        if existing.scalar_one_or_none():
            print(f"Użytkownik z emailem {email} już istnieje")
            sys.exit(1)

        org = await _resolve_org(db, organization_slug) if role != "super_admin" else None

        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            display_name=display_name,
            role=role,
            organization_id=org.id if org else None,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Utworzono {role}: {user.email} (id: {user.id})")


async def list_users() -> None:
    async with await _get_session() as db:
        result = await db.execute(
            select(User, Organization)
            .join(Organization, User.organization_id == Organization.id, isouter=True)
            .order_by(User.created_at)
        )
        rows = result.all()
        if not rows:
            print("Brak użytkowników")
            return
        for user, org in rows:
            status = "aktywny" if user.is_active else "nieaktywny"
            org_name = org.slug if org else "—"
            print(
                f"  {user.role:<11} | {user.email:<35} | {user.display_name:<20}"
                f" | {org_name:<15} | {status} | {user.id}"
            )


async def create_organization(name: str, slug: str) -> None:
    slug = slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9-]{2,64}", slug):
        print("Slug: a-z, 0-9, '-', 2–64 znaków")
        sys.exit(1)

    async with await _get_session() as db:
        existing = (
            await db.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none()
        if existing:
            print(f"Organizacja o slug '{slug}' już istnieje (id: {existing.id})")
            sys.exit(1)

        org = Organization(name=name.strip(), slug=slug)
        db.add(org)
        await db.commit()
        await db.refresh(org)
        print(f"Utworzono organizację: {org.name} ({org.slug}) — id: {org.id}")


async def list_organizations() -> None:
    async with await _get_session() as db:
        rows = (
            await db.execute(select(Organization).order_by(Organization.created_at))
        ).scalars().all()
        if not rows:
            print("Brak organizacji")
            return
        for o in rows:
            print(f"  {o.slug:<20} | {o.name:<40} | {o.id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dzialkowizja CLI")
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create-user", help="Utwórz użytkownika")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--role", default="user", choices=["super_admin", "admin", "user"])
    create.add_argument("--organization", default=None, help="Slug organizacji (dla admin/user)")

    super_admin = sub.add_parser("create-super-admin", help="Utwórz super admina (bootstrap)")
    super_admin.add_argument("--email", required=True)
    super_admin.add_argument("--name", required=True)
    super_admin.add_argument("--password", required=True)

    sub.add_parser("list-users", help="Lista użytkowników")

    create_org = sub.add_parser("create-organization", help="Utwórz organizację")
    create_org.add_argument("--name", required=True)
    create_org.add_argument("--slug", required=True)

    sub.add_parser("list-organizations", help="Lista organizacji")

    args = parser.parse_args()

    if args.command == "create-user":
        asyncio.run(
            create_user(args.email, args.name, args.password, args.role, args.organization)
        )
    elif args.command == "create-super-admin":
        asyncio.run(
            create_user(args.email, args.name, args.password, "super_admin", None)
        )
    elif args.command == "list-users":
        asyncio.run(list_users())
    elif args.command == "create-organization":
        asyncio.run(create_organization(args.name, args.slug))
    elif args.command == "list-organizations":
        asyncio.run(list_organizations())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
