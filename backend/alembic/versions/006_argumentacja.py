"""Argumentacja table — valuation arguments per plot.

1:1 with roszczenia by id_dzialki. Stores confidence score, model prices,
and up to 15 weighted text arguments explaining the valuation.

Revision ID: 006
Revises: 005
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_dzialki", sa.String(255), nullable=False),
        sa.Column("segment", sa.String(255), nullable=True),
        sa.Column("pow_m2", sa.Numeric(18, 4), nullable=True),
        sa.Column("pow_buforu", sa.Numeric(18, 4), nullable=True),
        sa.Column("procent_pow", sa.Numeric(8, 4), nullable=True),
        sa.Column("cena_ensemble", sa.Numeric(18, 2), nullable=True),
        sa.Column("wartosc_total", sa.Numeric(18, 2), nullable=True),
        sa.Column("cena_m2_roszczenie_orig", sa.Numeric(18, 2), nullable=True),
        sa.Column("wartosc_roszczenia_orig", sa.Numeric(18, 2), nullable=True),
        sa.Column("pewnosc_0_100", sa.Integer(), nullable=True),
        sa.Column("pewnosc_kategoria", sa.String(20), nullable=True),
        sa.Column("liczba_argumentow", sa.Integer(), nullable=True),
    ]
    # 15 argument + weight pairs
    for i in range(1, 16):
        cols.append(sa.Column(f"argument_{i}", sa.Text(), nullable=True))
        cols.append(sa.Column(f"argument_{i}_waga", sa.Integer(), nullable=True))

    op.create_table("argumentacja", *cols)
    op.create_index("ix_argumentacja_lot", "argumentacja", ["id_dzialki"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_argumentacja_lot", table_name="argumentacja")
    op.drop_table("argumentacja")
