"""Add wycena_supplemental table

Stores plot valuations from the supplemental wyceny_5_5M_*.csv sheet.
Used as a fallback when a plot is not present in roszczenia: the
spreadsheet covers a much wider set of plots but lacks owner/KW data.

Revision ID: 013
Revises: 012
Create Date: 2026-04-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wycena_supplemental",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_dzialki", sa.String(255), nullable=False),
        sa.Column("wartosc_dzialki", sa.Numeric(18, 2), nullable=False),
        sa.Column("cena_m2", sa.Numeric(18, 4), nullable=True),
        sa.Column("pow_dzialki", sa.Numeric(18, 4), nullable=True),
        sa.Column("pow_buforu", sa.Numeric(18, 4), nullable=True),
        sa.Column("segment_rynku", sa.String(64), nullable=True),
        sa.Column("pewnosc", sa.String(32), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_wycena_supplemental_lot",
        "wycena_supplemental",
        ["id_dzialki"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_wycena_supplemental_lot", table_name="wycena_supplemental")
    op.drop_table("wycena_supplemental")
