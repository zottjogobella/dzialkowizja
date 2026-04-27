"""Add ownership flags to roszczenia (sluzebnosci / 10+ owners / state owner)

The new roszczenia CSV (``roszczenia_keep_all_price55_sorted_prg_teryt.csv``)
ships three boolean flags per plot that the search dropdown surfaces as
small badges so users can spot complicated titles at a glance:

- ``hassluzebnosci``     → KW lists easements
- ``has10ormoreowners``  → 10 or more co-owners
- ``hasstateowner``      → state (Skarb Państwa / panstwo) is on the title

Stored as nullable booleans because rows ingested before this migration
have no source data — they remain NULL until the next ingest run.

Revision ID: 011
Revises: 010
Create Date: 2026-04-27
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roszczenia", sa.Column("has_sluzebnosci", sa.Boolean(), nullable=True))
    op.add_column("roszczenia", sa.Column("has_10_or_more_owners", sa.Boolean(), nullable=True))
    op.add_column("roszczenia", sa.Column("has_state_owner", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("roszczenia", "has_state_owner")
    op.drop_column("roszczenia", "has_10_or_more_owners")
    op.drop_column("roszczenia", "has_sluzebnosci")
