"""Replace 'user' role with 'handlowiec' + 'prawnik'; restrictions per role

The single ``user`` tier is split into two equal-tier roles. Org admins
can configure visibility separately for each — ``restricted_fields`` gains
a ``role`` column and the PK becomes (organization_id, role, field_key).

Backfill:
- ``users.role = 'user'`` → ``handlowiec`` (arbitrary default; admin can
  re-assign per user via /api/admin endpoints).
- Existing ``restricted_fields`` rows are duplicated for both new roles
  so current visibility behaviour for legacy users is preserved.

Revision ID: 014
Revises: 013
Create Date: 2026-04-28
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Swap the user_role enum (drop 'user', add handlowiec + prawnik) ──
    # Default references the old type, so it has to come off before the swap.
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")

    op.execute(
        "CREATE TYPE user_role_new AS ENUM ('super_admin', 'admin', 'handlowiec', 'prawnik')"
    )
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role_new
        USING (
            CASE role::text
                WHEN 'user' THEN 'handlowiec'
                ELSE role::text
            END
        )::user_role_new
        """
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_new RENAME TO user_role")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'handlowiec'::user_role")

    # ── 2. Add role column to restricted_fields ──
    op.add_column(
        "restricted_fields",
        sa.Column("role", sa.String(32), nullable=True),
    )

    # Drop the old PK first — we need to insert duplicate (org, field_key)
    # rows differing only by role, which the original PK forbids.
    op.execute("ALTER TABLE restricted_fields DROP CONSTRAINT restricted_fields_pkey")

    # Duplicate every existing row for the second role, then label originals
    # as handlowiec. Net effect: legacy restrictions apply to both new roles.
    op.execute(
        """
        INSERT INTO restricted_fields (organization_id, field_key, role, created_at)
        SELECT organization_id, field_key, 'prawnik', created_at
        FROM restricted_fields
        WHERE role IS NULL
        """
    )
    op.execute("UPDATE restricted_fields SET role = 'handlowiec' WHERE role IS NULL")

    op.alter_column("restricted_fields", "role", nullable=False)
    op.create_primary_key(
        "restricted_fields_pkey",
        "restricted_fields",
        ["organization_id", "role", "field_key"],
    )


def downgrade() -> None:
    # ── 1. Collapse restricted_fields back to (org, field_key) ──
    op.execute("ALTER TABLE restricted_fields DROP CONSTRAINT restricted_fields_pkey")
    # Keep one row per (org, field_key) — drop the prawnik duplicates.
    op.execute("DELETE FROM restricted_fields WHERE role = 'prawnik'")
    op.drop_column("restricted_fields", "role")
    op.create_primary_key(
        "restricted_fields_pkey",
        "restricted_fields",
        ["organization_id", "field_key"],
    )

    # ── 2. Revert enum: handlowiec/prawnik → user ──
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("CREATE TYPE user_role_old AS ENUM ('super_admin', 'admin', 'user')")
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE user_role_old
        USING (
            CASE role::text
                WHEN 'handlowiec' THEN 'user'
                WHEN 'prawnik' THEN 'user'
                ELSE role::text
            END
        )::user_role_old
        """
    )
    op.execute("DROP TYPE user_role")
    op.execute("ALTER TYPE user_role_old RENAME TO user_role")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user'::user_role")
