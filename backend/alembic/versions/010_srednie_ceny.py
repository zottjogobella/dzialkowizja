"""Average RCN prices per powiat and gmina.

Three read-only reference tables loaded from ``srednie_ceny_rcn.sqlite``:

- ``srednie_ceny_gmina``        — per gmina TERYT × rodzaj_nieruchomosci
- ``srednie_ceny_powiat_total`` — per powiat TERYT × rodzaj_nieruchomosci
- ``srednie_ceny_powiat``       — per powiat TERYT × rodzaj × segment_rynku

Lives in the app DB (not gruntomat/transakcje) because it's produced by
this project's own aggregation pipeline and small enough (~15k rows total)
to join freely with our own tables.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "srednie_ceny_gmina",
        sa.Column("gmina", sa.String(12), primary_key=True),
        sa.Column("rodzaj_nieruchomosci", sa.SmallInteger(), primary_key=True),
        sa.Column("teryt_powiat", sa.String(8), nullable=False),
        sa.Column("wojewodztwo", sa.String(4), nullable=False),
        sa.Column("rodzaj_nazwa", sa.Text(), nullable=True),
        sa.Column("liczba_transakcji", sa.Integer(), nullable=False),
        sa.Column("cena_za_m2_srednia", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_mediana", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_q1", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_q3", sa.Numeric(14, 2), nullable=True),
        sa.Column("pow_m2_srednia", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_transakcji_srednia", sa.Numeric(16, 2), nullable=True),
        sa.Column("rok_min", sa.SmallInteger(), nullable=True),
        sa.Column("rok_max", sa.SmallInteger(), nullable=True),
    )
    op.create_index(
        "ix_srednie_ceny_gmina_powiat", "srednie_ceny_gmina", ["teryt_powiat"]
    )

    op.create_table(
        "srednie_ceny_powiat_total",
        sa.Column("teryt", sa.String(8), primary_key=True),
        sa.Column("rodzaj_nieruchomosci", sa.SmallInteger(), primary_key=True),
        sa.Column("wojewodztwo", sa.String(4), nullable=False),
        sa.Column("rodzaj_nazwa", sa.Text(), nullable=True),
        sa.Column("liczba_transakcji", sa.Integer(), nullable=False),
        sa.Column("cena_za_m2_srednia", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_mediana", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_q1", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_q3", sa.Numeric(14, 2), nullable=True),
        sa.Column("pow_m2_srednia", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_transakcji_srednia", sa.Numeric(16, 2), nullable=True),
        sa.Column("rok_min", sa.SmallInteger(), nullable=True),
        sa.Column("rok_max", sa.SmallInteger(), nullable=True),
    )

    op.create_table(
        "srednie_ceny_powiat",
        sa.Column("teryt", sa.String(8), primary_key=True),
        sa.Column("rodzaj_nieruchomosci", sa.SmallInteger(), primary_key=True),
        sa.Column("segment_rynku", sa.String(32), primary_key=True),
        sa.Column("wojewodztwo", sa.String(4), nullable=False),
        sa.Column("rodzaj_nazwa", sa.Text(), nullable=True),
        sa.Column("liczba_transakcji", sa.Integer(), nullable=False),
        sa.Column("cena_za_m2_srednia", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_mediana", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_q1", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_q3", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_za_m2_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("pow_m2_srednia", sa.Numeric(14, 2), nullable=True),
        sa.Column("cena_transakcji_srednia", sa.Numeric(16, 2), nullable=True),
        sa.Column("rok_min", sa.SmallInteger(), nullable=True),
        sa.Column("rok_max", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("srednie_ceny_powiat")
    op.drop_table("srednie_ceny_powiat_total")
    op.drop_index("ix_srednie_ceny_gmina_powiat", table_name="srednie_ceny_gmina")
    op.drop_table("srednie_ceny_gmina")
