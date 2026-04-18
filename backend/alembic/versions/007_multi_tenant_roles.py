"""Multi-tenant: organizations, role enum, restricted fields, activity log

Adds:
- ``organizations`` table
- ``users.role`` (super_admin | admin | user), ``organization_id``, ``invited_by_user_id``
- ``restricted_fields`` (per-org list of field keys hidden from role=user)
- ``activity_log`` (auditable trail of data-access actions with IP)

Backfill rule: oldest existing user becomes ``super_admin`` (no org). Any
remaining existing users become ``admin`` of a freshly created
"Default Organization". This keeps the current single-tenant deploy working
without manual intervention after ``alembic upgrade head``.

Revision ID: 007
Revises: 006
Create Date: 2026-04-18
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Stable UUID for the auto-created default organization. Referenced from
# the backfill block; kept as a constant so the downgrade can target it.
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

USER_ROLE_ENUM = "user_role"


def upgrade() -> None:
    # Postgres enum type. Created explicitly so we can reuse it across columns
    # and reference it in raw SQL during backfill.
    op.execute(
        f"CREATE TYPE {USER_ROLE_ENUM} AS ENUM ('super_admin', 'admin', 'user')"
    )

    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("super_admin", "admin", "user", name=USER_ROLE_ENUM, create_type=False),
            nullable=False,
            server_default="user",
        ),
    )
    op.add_column(
        "users",
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("invited_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_users_organization", "users", ["organization_id"])

    op.create_table(
        "restricted_fields",
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("field_key", sa.String(128), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "activity_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=True),
        sa.Column("query_text", sa.String(500), nullable=True),
        sa.Column("ip_address", INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_activity_log_user_time", "activity_log", ["user_id", "created_at"])
    op.create_index("ix_activity_log_org_time", "activity_log", ["organization_id", "created_at"])

    # Backfill: keep current single-tenant deploy working by promoting the
    # earliest user to super_admin and parking everyone else as admin in a
    # default organization.
    bind = op.get_bind()
    user_count = bind.execute(sa.text("SELECT count(*) FROM users")).scalar() or 0
    if user_count > 0:
        bind.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"
            ),
            {"id": DEFAULT_ORG_ID, "name": "Default Organization", "slug": "default"},
        )

        first_user_id = bind.execute(
            sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")
        ).scalar()

        # Stamp the org's creator now that we know the first user
        bind.execute(
            sa.text("UPDATE organizations SET created_by_user_id = :uid WHERE id = :oid"),
            {"uid": first_user_id, "oid": DEFAULT_ORG_ID},
        )

        bind.execute(
            sa.text(
                f"UPDATE users SET role = 'super_admin'::{USER_ROLE_ENUM}, organization_id = NULL WHERE id = :uid"
            ),
            {"uid": first_user_id},
        )
        bind.execute(
            sa.text(
                f"UPDATE users SET role = 'admin'::{USER_ROLE_ENUM}, organization_id = :oid WHERE id != :uid"
            ),
            {"uid": first_user_id, "oid": DEFAULT_ORG_ID},
        )


def downgrade() -> None:
    op.drop_index("ix_activity_log_org_time", table_name="activity_log")
    op.drop_index("ix_activity_log_user_time", table_name="activity_log")
    op.drop_table("activity_log")

    op.drop_table("restricted_fields")

    op.drop_index("ix_users_organization", table_name="users")
    op.drop_constraint("users_invited_by_user_id_fkey", "users", type_="foreignkey")
    op.drop_constraint("users_organization_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "invited_by_user_id")
    op.drop_column("users", "organization_id")
    op.drop_column("users", "role")

    op.drop_table("organizations")

    op.execute(f"DROP TYPE {USER_ROLE_ENUM}")
