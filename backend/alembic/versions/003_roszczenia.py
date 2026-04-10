"""Add roszczenia table for loaded claim spreadsheet

Revision ID: 003
Revises: 002
Create Date: 2026-04-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roszczenia",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id_dzialki", sa.String(255), nullable=False),
        sa.Column("wartosc_roszczenia", sa.Numeric(18, 2), nullable=False),
    )
    op.create_index("ix_roszczenia_lot", "roszczenia", ["id_dzialki"])


def downgrade() -> None:
    op.drop_index("ix_roszczenia_lot", table_name="roszczenia")
    op.drop_table("roszczenia")
