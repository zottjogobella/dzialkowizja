#!/usr/bin/env python3
"""Load roszczenia.csv into the dzialkowizja app DB.

CSV schema (columns kept):
    lot_identifier  → roszczenia.id_dzialki
    wycena          → roszczenia.wartosc_dzialki   (total plot value)

Note: despite this file being named "roszczenia.csv", the stored value
is the **plot valuation** (cena_m2 × pow_dzialki), NOT a pre-computed
claim. The claim is derived live in the frontend as
``wartosc_dzialki × 0.5 × (pow_buforu / pow_dzialki)`` so that moving
the buffer slider rescales the claim to the current coverage.

Rows are filtered to owner types we care about for the claim display
(``os prawna`` and ``panstwo``). Individuals (``os fizyczna``) make up
~94% of the file but are privacy-sensitive and not part of this feature.

Usage::

    python backend/scripts/ingest_roszczenia_csv.py /path/to/roszczenia.csv

Connection details come from the usual ``DATABASE_URL_SYNC`` env var (the
same one alembic reads), so locally you point it at your dev app DB and
on the VPS you run it inside the backend container where the var is
already set.

Idempotent: truncates the table before inserting so re-runs give a clean
state.
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

logger = logging.getLogger("ingest_roszczenia_csv")

KEPT_OWNER_TYPES = {"os prawna", "panstwo"}
BATCH_SIZE = 5000


def parse_database_url(url: str) -> dict:
    """Convert SQLAlchemy-style ``postgresql://`` into psycopg2 kwargs."""
    import urllib.parse

    # Strip async driver suffix if present (``postgresql+asyncpg://``).
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


def read_rows(csv_path: Path) -> Iterator[tuple[str, float]]:
    """Stream (id_dzialki, wartosc_dzialki) from the CSV."""
    seen_per_plot: dict[str, float] = {}
    total = 0
    kept = 0
    bad = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"lot_identifier", "owners_type", "wycena"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                f"CSV is missing required columns: {sorted(missing)}. "
                f"Found: {reader.fieldnames}"
            )
        for row in reader:
            total += 1
            if row.get("owners_type") not in KEPT_OWNER_TYPES:
                continue
            lot = (row.get("lot_identifier") or "").strip()
            raw_value = (row.get("wycena") or "").strip()
            if not lot or not raw_value:
                bad += 1
                continue
            try:
                value = float(raw_value)
            except ValueError:
                bad += 1
                continue
            # A single plot can appear multiple times (multiple owners /
            # multiple source files). Keep the largest plot valuation so
            # we expose the most conservative figure to the user.
            prev = seen_per_plot.get(lot)
            if prev is None or value > prev:
                seen_per_plot[lot] = value
                if prev is None:
                    kept += 1
            if total % 100_000 == 0:
                logger.info("... read %d rows (kept unique plots: %d)", total, kept)

    logger.info(
        "scanned %d rows → %d unique plots kept (%d dropped as malformed)",
        total,
        kept,
        bad,
    )
    for lot, value in seen_per_plot.items():
        yield lot, value


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

    conn = psycopg2.connect(**conn_kwargs)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE roszczenia RESTART IDENTITY")
            batch: list[tuple[str, float]] = []
            written = 0
            for lot, value in read_rows(args.csv_path):
                batch.append((lot, value))
                if len(batch) >= BATCH_SIZE:
                    psycopg2.extras.execute_values(
                        cur,
                        "INSERT INTO roszczenia (id_dzialki, wartosc_dzialki) VALUES %s",
                        batch,
                    )
                    written += len(batch)
                    if written % 20_000 == 0:
                        logger.info("inserted %d rows", written)
                    batch.clear()
            if batch:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO roszczenia (id_dzialki, wartosc_dzialki) VALUES %s",
                    batch,
                )
                written += len(batch)

        conn.commit()
        logger.info("done — %d rows in roszczenia", written)
    except Exception:
        conn.rollback()
        logger.exception("ingest failed; rolled back")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
