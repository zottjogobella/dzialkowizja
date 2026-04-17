#!/usr/bin/env python3
"""Load roszczenia_argumentacja.csv into the argumentacja table.

CSV has ~483K rows (1:1 with roszczenia by id_dzialki). Stores model
prices, confidence scores, and up to 15 weighted text arguments per plot.

Usage::

    python backend/scripts/ingest_argumentacja_csv.py /path/to/roszczenia_argumentacja.csv

Idempotent: truncates the table before inserting.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Iterator

import psycopg2
import psycopg2.extras

logger = logging.getLogger("ingest_argumentacja")

BATCH_SIZE = 5000

DB_COLUMNS = [
    "id_dzialki",
    "segment",
    "pow_m2",
    "pow_buforu",
    "procent_pow",
    "cena_ensemble",
    "wartosc_total",
    "cena_m2_roszczenie_orig",
    "wartosc_roszczenia_orig",
    "pewnosc_0_100",
    "pewnosc_kategoria",
    "liczba_argumentow",
]
# Add argument_1..15 + argument_1_waga..15_waga
for _i in range(1, 16):
    DB_COLUMNS.append(f"argument_{_i}")
    DB_COLUMNS.append(f"argument_{_i}_waga")

NUMERIC_COLS = {
    "pow_m2", "pow_buforu", "procent_pow",
    "cena_ensemble", "wartosc_total",
    "cena_m2_roszczenie_orig", "wartosc_roszczenia_orig",
}
INT_COLS = {"pewnosc_0_100", "liczba_argumentow"} | {
    f"argument_{i}_waga" for i in range(1, 16)
}


def parse_database_url(url: str) -> dict:
    import urllib.parse
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


def _convert(col: str, raw: str):
    """Convert a raw CSV string to the appropriate Python type."""
    val = raw.strip()
    if not val:
        return None
    if col in NUMERIC_COLS:
        try:
            return float(val)
        except ValueError:
            return None
    if col in INT_COLS:
        try:
            return int(float(val))
        except ValueError:
            return None
    return val


def read_rows(csv_path: Path) -> Iterator[tuple]:
    seen: set[str] = set()
    total = 0
    kept = 0
    # Increase field size limit for large text arguments
    csv.field_size_limit(1_000_000)
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        if "id_dzialki" not in fieldnames:
            raise SystemExit(f"CSV missing 'id_dzialki'. Found: {sorted(fieldnames)}")
        for row in reader:
            total += 1
            lot = (row.get("id_dzialki") or "").strip()
            if not lot or lot in seen:
                continue
            seen.add(lot)
            kept += 1
            values = []
            for col in DB_COLUMNS:
                values.append(_convert(col, row.get(col, "")))
            yield tuple(values)
            if total % 100_000 == 0:
                logger.info("... read %d rows (kept: %d)", total, kept)

    logger.info("scanned %d rows → %d unique plots", total, kept)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", type=Path)
    ap.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL_SYNC"),
        help="Postgres URL (default: $DATABASE_URL_SYNC)",
    )
    args = ap.parse_args(argv)

    if not args.csv_path.exists():
        ap.error(f"CSV not found: {args.csv_path}")
    if not args.database_url:
        ap.error("DATABASE_URL_SYNC not set and --database-url not given")

    conn_kwargs = parse_database_url(args.database_url)
    logger.info("connecting to %s:%s/%s as %s",
                conn_kwargs["host"], conn_kwargs["port"],
                conn_kwargs["dbname"], conn_kwargs["user"])

    cols_sql = ", ".join(DB_COLUMNS)
    insert_sql = f"INSERT INTO argumentacja ({cols_sql}) VALUES %s"

    conn = psycopg2.connect(**conn_kwargs)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE argumentacja RESTART IDENTITY")
            batch: list[tuple] = []
            written = 0
            for values in read_rows(args.csv_path):
                batch.append(values)
                if len(batch) >= BATCH_SIZE:
                    psycopg2.extras.execute_values(cur, insert_sql, batch)
                    written += len(batch)
                    if written % 20_000 == 0:
                        logger.info("inserted %d rows", written)
                    batch.clear()
            if batch:
                psycopg2.extras.execute_values(cur, insert_sql, batch)
                written += len(batch)

        conn.commit()
        logger.info("done — %d rows in argumentacja", written)
    except Exception:
        conn.rollback()
        logger.exception("ingest failed; rolled back")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
