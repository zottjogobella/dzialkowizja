"""Rename roszczenia.wartosc_roszczenia → wartosc_dzialki

We originally loaded the CSV's wartosc_roszczenia column (a pre-computed
claim value = pow_buforu × cena_m2 × 0.5), but the correct feature is to
hold the plot valuation (cena_m2 × pow_dzialki, i.e. the CSV's `wycena`
column) and derive the claim live as
``wartosc_dzialki × 0.5 × (pow_buforu / pow_dzialki)``.

The data loaded into the old column will be overwritten by a fresh
ingest of the `wycena` column anyway, so this migration just renames —
no data conversion.

Revision ID: 004
Revises: 003
Create Date: 2026-04-11
"""
from typing import Sequence, Union

from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "roszczenia", "wartosc_roszczenia", new_column_name="wartosc_dzialki"
    )


def downgrade() -> None:
    op.alter_column(
        "roszczenia", "wartosc_dzialki", new_column_name="wartosc_roszczenia"
    )
