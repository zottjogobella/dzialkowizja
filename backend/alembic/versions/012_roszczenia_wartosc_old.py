"""Add wartosc_dzialki_old to roszczenia

Stores the prior plot valuation from the CSV's ``wycena_old`` column so
the UI can show "wartość poprzednia" next to the current figure.
Nullable because rows ingested from older CSVs (without that column)
have no source data.

Revision ID: 012
Revises: 011
Create Date: 2026-04-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roszczenia",
        sa.Column("wartosc_dzialki_old", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("roszczenia", "wartosc_dzialki_old")
