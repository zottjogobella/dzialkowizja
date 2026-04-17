"""Add kw and entities columns to roszczenia

Loaded for the subset of plots present in roszczenia.csv — KW (księga
wieczysta / land registry number) and entities (owner names + type).

Revision ID: 005
Revises: 004
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("roszczenia", sa.Column("kw", sa.String(64), nullable=True))
    op.add_column("roszczenia", sa.Column("entities", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("roszczenia", "entities")
    op.drop_column("roszczenia", "kw")
