#!/usr/bin/env python3
"""Load srednie_ceny_rcn.sqlite into the dzialkowizja app DB.

Source sqlite has three tables we copy verbatim:
    gmina_ceny         → srednie_ceny_gmina
    powiat_ceny_total  → srednie_ceny_powiat_total
    powiat_ceny        → srednie_ceny_powiat (per segment_rynku)

Idempotent: TRUNCATE + INSERT. Safe to re-run on every data refresh.

Usage::

    python backend/scripts/ingest_srednie_ceny_sqlite.py /path/to/srednie_ceny_rcn.sqlite

Reads ``DATABASE_URL_SYNC`` for app-DB connection (set in the backend
container env).
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import urllib.parse
from pathlib import Path

import psycopg2
import psycopg2.extras

logger = logging.getLogger("ingest_srednie_ceny")

BATCH_SIZE = 2000


def parse_database_url(url: str) -> dict:
    if "+" in url.split("://", 1)[0]:
        scheme, rest = url.split("://", 1)
        url = scheme.split("+", 1)[0] + "://" + rest
    p = urllib.parse.urlparse(url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "dbname": (p.path or "/").lstrip("/"),
        "user": p.username,
        "password": p.password,
    }


# (sqlite_table, pg_table, [(sqlite_col, pg_col), ...])
# Listed in order matching the alembic migration schema.
TABLE_MAP = [
    (
        "gmina_ceny",
        "srednie_ceny_gmina",
        [
            ("gmina", "gmina"),
            ("rodzaj_nieruchomosci", "rodzaj_nieruchomosci"),
            ("teryt_powiat", "teryt_powiat"),
            ("wojewodztwo", "wojewodztwo"),
            ("rodzaj_nazwa", "rodzaj_nazwa"),
            ("liczba_transakcji", "liczba_transakcji"),
            ("cena_za_m2_srednia", "cena_za_m2_srednia"),
            ("cena_za_m2_mediana", "cena_za_m2_mediana"),
            ("cena_za_m2_q1", "cena_za_m2_q1"),
            ("cena_za_m2_q3", "cena_za_m2_q3"),
            ("pow_m2_srednia", "pow_m2_srednia"),
            ("cena_transakcji_srednia", "cena_transakcji_srednia"),
            ("rok_min", "rok_min"),
            ("rok_max", "rok_max"),
        ],
    ),
    (
        "powiat_ceny_total",
        "srednie_ceny_powiat_total",
        [
            ("teryt", "teryt"),
            ("rodzaj_nieruchomosci", "rodzaj_nieruchomosci"),
            ("wojewodztwo", "wojewodztwo"),
            ("rodzaj_nazwa", "rodzaj_nazwa"),
            ("liczba_transakcji", "liczba_transakcji"),
            ("cena_za_m2_srednia", "cena_za_m2_srednia"),
            ("cena_za_m2_mediana", "cena_za_m2_mediana"),
            ("cena_za_m2_q1", "cena_za_m2_q1"),
            ("cena_za_m2_q3", "cena_za_m2_q3"),
            ("pow_m2_srednia", "pow_m2_srednia"),
            ("cena_transakcji_srednia", "cena_transakcji_srednia"),
            ("rok_min", "rok_min"),
            ("rok_max", "rok_max"),
        ],
    ),
    (
        "powiat_ceny",
        "srednie_ceny_powiat",
        [
            ("teryt", "teryt"),
            ("rodzaj_nieruchomosci", "rodzaj_nieruchomosci"),
            ("segment_rynku", "segment_rynku"),
            ("wojewodztwo", "wojewodztwo"),
            ("rodzaj_nazwa", "rodzaj_nazwa"),
            ("liczba_transakcji", "liczba_transakcji"),
            ("cena_za_m2_srednia", "cena_za_m2_srednia"),
            ("cena_za_m2_mediana", "cena_za_m2_mediana"),
            ("cena_za_m2_q1", "cena_za_m2_q1"),
            ("cena_za_m2_q3", "cena_za_m2_q3"),
            ("cena_za_m2_min", "cena_za_m2_min"),
            ("cena_za_m2_max", "cena_za_m2_max"),
            ("pow_m2_srednia", "pow_m2_srednia"),
            ("cena_transakcji_srednia", "cena_transakcji_srednia"),
            ("rok_min", "rok_min"),
            ("rok_max", "rok_max"),
        ],
    ),
]


def copy_table(
    sqlite_cur, pg_cur, sqlite_table: str, pg_table: str, cols: list[tuple[str, str]]
) -> int:
    # Some sqlite rows have rodzaj_nieruchomosci=NULL (rodzaj_nazwa='inna').
    # The destination PK doesn't allow NULL, so coerce to 0 (= "inna/unknown").
    # Same for segment_rynku in the powiat segment table.
    def sel(col):
        if col == "rodzaj_nieruchomosci":
            return "COALESCE(rodzaj_nieruchomosci, 0) AS rodzaj_nieruchomosci"
        if col == "segment_rynku":
            return "COALESCE(segment_rynku, 'INNE') AS segment_rynku"
        return col
    sq_cols = ", ".join(sel(c[0]) for c in cols)
    pg_cols = ", ".join(c[1] for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    insert_sql = f"INSERT INTO {pg_table} ({pg_cols}) VALUES ({placeholders})"

    pg_cur.execute(f"TRUNCATE {pg_table}")
    sqlite_cur.execute(f"SELECT {sq_cols} FROM {sqlite_table}")
    buf: list[tuple] = []
    n = 0
    for row in sqlite_cur:
        buf.append(tuple(row))
        if len(buf) >= BATCH_SIZE:
            psycopg2.extras.execute_batch(pg_cur, insert_sql, buf, page_size=BATCH_SIZE)
            n += len(buf)
            buf.clear()
    if buf:
        psycopg2.extras.execute_batch(pg_cur, insert_sql, buf, page_size=BATCH_SIZE)
        n += len(buf)
    return n


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sqlite_path", type=Path)
    args = ap.parse_args(argv)

    if not args.sqlite_path.exists():
        logger.error("sqlite not found: %s", args.sqlite_path)
        return 1

    url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    if not url:
        logger.error("DATABASE_URL_SYNC (or DATABASE_URL) not set")
        return 1
    kw = parse_database_url(url)
    kw["connect_timeout"] = 30

    logger.info("opening sqlite %s", args.sqlite_path)
    sq = sqlite3.connect(str(args.sqlite_path))
    sq_cur = sq.cursor()

    logger.info("connecting to app DB %s:%s/%s", kw["host"], kw["port"], kw["dbname"])
    pg = psycopg2.connect(**kw)
    try:
        with pg.cursor() as pg_cur:
            for sqlite_table, pg_table, cols in TABLE_MAP:
                logger.info("loading %s -> %s", sqlite_table, pg_table)
                n = copy_table(sq_cur, pg_cur, sqlite_table, pg_table, cols)
                logger.info("  inserted %d rows", n)
        pg.commit()
    finally:
        pg.close()
        sq.close()
    logger.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
