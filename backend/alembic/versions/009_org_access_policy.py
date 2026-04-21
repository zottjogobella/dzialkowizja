"""Add login-hours schedule and daily search limit per organization.

Adds three columns to ``organizations`` controlling the two features, plus
a new ``organization_login_hours`` table carrying 7 rows per org (one per
day of week). Backfills every existing organization with the product
default: Mon-Fri 09:00-18:00 open, Sat-Sun closed, login-hours enabled,
daily search limit enabled at 40.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "login_hours_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "daily_search_limit_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "daily_search_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("40"),
        ),
    )

    op.create_table(
        "organization_login_hours",
        sa.Column(
            "organization_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day_of_week", sa.SmallInteger(), primary_key=True),
        sa.Column(
            "closed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_login_hours_dow_range",
        ),
        sa.CheckConstraint(
            "closed OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)",
            name="ck_login_hours_window",
        ),
    )

    # Backfill every existing org with Mon-Fri 09:00-18:00, Sat-Sun closed.
    op.execute(
        """
        INSERT INTO organization_login_hours (organization_id, day_of_week, closed, start_time, end_time)
        SELECT o.id, dow, FALSE, TIME '09:00', TIME '18:00'
        FROM organizations o
        CROSS JOIN generate_series(0, 4) AS dow
        """
    )
    op.execute(
        """
        INSERT INTO organization_login_hours (organization_id, day_of_week, closed, start_time, end_time)
        SELECT o.id, dow, TRUE, NULL, NULL
        FROM organizations o
        CROSS JOIN generate_series(5, 6) AS dow
        """
    )


def downgrade() -> None:
    op.drop_table("organization_login_hours")
    op.drop_column("organizations", "daily_search_limit")
    op.drop_column("organizations", "daily_search_limit_enabled")
    op.drop_column("organizations", "login_hours_enabled")
