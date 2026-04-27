"""Per-role login hours and daily search limit

Splits the org-level access policy into per-role policies, mirroring the
restricted_fields split done in 014. Each org now configures handlowiec
and prawnik independently.

Schema changes:
- ``organization_login_hours`` gains ``role`` (PK becomes
  (org, role, dow)). Existing rows are duplicated for both roles so legacy
  schedules keep applying to both tiers after upgrade.
- New ``organization_role_policy(org, role, login_hours_enabled,
  daily_search_limit_enabled, daily_search_limit)`` replaces the three
  org-level columns. Seeded from the existing org-level values for both
  roles.
- The three replaced columns on ``organizations`` are dropped.

Revision ID: 015
Revises: 014
Create Date: 2026-04-28
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. organization_login_hours: add role to PK ──
    op.add_column(
        "organization_login_hours",
        sa.Column("role", sa.String(32), nullable=True),
    )
    op.execute(
        "ALTER TABLE organization_login_hours DROP CONSTRAINT organization_login_hours_pkey"
    )
    # Duplicate every legacy row for prawnik, then label the originals.
    op.execute(
        """
        INSERT INTO organization_login_hours
            (organization_id, day_of_week, role, closed, start_time, end_time)
        SELECT organization_id, day_of_week, 'prawnik', closed, start_time, end_time
        FROM organization_login_hours
        WHERE role IS NULL
        """
    )
    op.execute("UPDATE organization_login_hours SET role = 'handlowiec' WHERE role IS NULL")
    op.alter_column("organization_login_hours", "role", nullable=False)
    op.create_primary_key(
        "organization_login_hours_pkey",
        "organization_login_hours",
        ["organization_id", "role", "day_of_week"],
    )

    # ── 2. New organization_role_policy table ──
    op.create_table(
        "organization_role_policy",
        sa.Column(
            "organization_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(32), primary_key=True),
        sa.Column(
            "login_hours_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "daily_search_limit_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "daily_search_limit",
            sa.Integer,
            nullable=False,
            server_default=sa.text("40"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Seed: copy the org-level policy into both role rows so behaviour
    # carries over unchanged.
    op.execute(
        """
        INSERT INTO organization_role_policy
            (organization_id, role, login_hours_enabled,
             daily_search_limit_enabled, daily_search_limit)
        SELECT id, 'handlowiec', login_hours_enabled,
               daily_search_limit_enabled, daily_search_limit
        FROM organizations
        UNION ALL
        SELECT id, 'prawnik', login_hours_enabled,
               daily_search_limit_enabled, daily_search_limit
        FROM organizations
        """
    )

    # ── 3. Drop now-redundant org-level columns ──
    op.drop_column("organizations", "login_hours_enabled")
    op.drop_column("organizations", "daily_search_limit_enabled")
    op.drop_column("organizations", "daily_search_limit")


def downgrade() -> None:
    # ── 3. Restore org-level columns ──
    op.add_column(
        "organizations",
        sa.Column(
            "login_hours_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "daily_search_limit_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "daily_search_limit",
            sa.Integer,
            nullable=False,
            server_default=sa.text("40"),
        ),
    )
    # Pull handlowiec settings back to org-level (arbitrary choice — both
    # roles should match for legacy data anyway).
    op.execute(
        """
        UPDATE organizations o
        SET login_hours_enabled = p.login_hours_enabled,
            daily_search_limit_enabled = p.daily_search_limit_enabled,
            daily_search_limit = p.daily_search_limit
        FROM organization_role_policy p
        WHERE p.organization_id = o.id AND p.role = 'handlowiec'
        """
    )

    # ── 2. Drop per-role policy table ──
    op.drop_table("organization_role_policy")

    # ── 1. Collapse organization_login_hours back to (org, dow) ──
    op.execute(
        "ALTER TABLE organization_login_hours DROP CONSTRAINT organization_login_hours_pkey"
    )
    op.execute("DELETE FROM organization_login_hours WHERE role = 'prawnik'")
    op.drop_column("organization_login_hours", "role")
    op.create_primary_key(
        "organization_login_hours_pkey",
        "organization_login_hours",
        ["organization_id", "day_of_week"],
    )
