"""Add plot_snapshots table

Revision ID: 002
Revises: 001
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plot_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("id_dzialki", sa.String(255), nullable=False),
        sa.Column("snapshot_type", sa.String(20), nullable=False),
        sa.Column("image_data", sa.LargeBinary, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_plot_snapshots_dzialki_type",
        "plot_snapshots",
        ["id_dzialki", "snapshot_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("plot_snapshots")
