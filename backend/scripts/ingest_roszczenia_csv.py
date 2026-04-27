#!/usr/bin/env python3
"""Load roszczenia.csv into the dzialkowizja app DB.

CSV schema (columns kept):
    lot_identifier      → roszczenia.id_dzialki
    wycena              → roszczenia.wartosc_dzialki   (current total plot value)
    wycena_old          → roszczenia.wartosc_dzialki_old (prior total plot value, optional)
    kw                  → roszczenia.kw                (land registry number, optional)
    entities            → roszczenia.entities          (owner names + type, optional)
    hassluzebnosci      → roszczenia.has_sluzebnosci      (0/1 → bool, optional)
    has10ormoreowners   → roszczenia.has_10_or_more_owners (0/1 → bool, optional)
    hasstateowner       → roszczenia.has_state_owner       (0/1 → bool, optional)

Note: despite this file being named "roszczenia.csv", the stored value
is the **plot valuation** (cena_m2 × pow_dzialki), NOT a pre-computed
claim. The claim is derived live in the frontend as
``wartosc_dzialki × 0.5 × (pow_buforu / pow_dzialki)`` so that moving
the buffer slider rescales the claim to the current coverage.

All rows with a usable valuation are loaded regardless of owner type —
if the CSV has KW + entities for a plot we want to show them.

The flag columns are optional — older CSVs without them load fine and
the columns are left NULL.

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

BATCH_SIZE = 5000

# CSV's csv.field_size_limit defaults to 128 KB — some entity strings
# (long owner lists) exceed that on the bigger sheets, so bump it up.
csv.field_size_limit(sys.maxsize)


Row = tuple[
    str,            # id_dzialki
    float,          # wartosc_dzialki
    float | None,   # wartosc_dzialki_old
    str | None,     # kw
    str | None,     # entities
    bool | None,    # has_sluzebnosci
    bool | None,    # has_10_or_more_owners
    bool | None,    # has_state_owner
]


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


def _parse_flag(raw: str) -> bool | None:
    """Parse a 0/1/empty CSV field as bool|None.

    Anything other than the literal "0" or "1" (after strip) returns None
    so a stray value doesn't silently get coerced to False.
    """
    s = (raw or "").strip()
    if s == "1":
        return True
    if s == "0":
        return False
    return None


def _parse_money(raw: str) -> float | None:
    """Parse an optional zł float; return None on empty/non-numeric."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_rows(csv_path: Path) -> Iterator[Row]:
    """Stream deduped rows from the CSV.

    `kw`, `entities`, the flag columns and ``wartosc_dzialki_old`` are
    informational and copied through as-is; we keep whichever row wins the
    wartosc_dzialki tiebreak so all displayed fields come from the same
    source row.
    """
    Kept = tuple[float, float | None, str | None, str | None, bool | None, bool | None, bool | None]
    seen_per_plot: dict[str, Kept] = {}
    total = 0
    kept = 0
    bad = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"lot_identifier", "wycena"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                f"CSV is missing required columns: {sorted(missing)}. "
                f"Found: {reader.fieldnames}"
            )
        fields = set(reader.fieldnames or [])
        has_kw = "kw" in fields
        has_entities = "entities" in fields
        has_wycena_old = "wycena_old" in fields
        has_sluzebnosci = "hassluzebnosci" in fields
        has_10plus = "has10ormoreowners" in fields
        has_state = "hasstateowner" in fields
        for row in reader:
            total += 1
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
            value_old = _parse_money(row.get("wycena_old", "")) if has_wycena_old else None
            kw = (row.get("kw") or "").strip() if has_kw else ""
            entities = (row.get("entities") or "").strip() if has_entities else ""
            kw_val: str | None = kw or None
            entities_val: str | None = entities or None
            sluz = _parse_flag(row.get("hassluzebnosci", "")) if has_sluzebnosci else None
            ten = _parse_flag(row.get("has10ormoreowners", "")) if has_10plus else None
            state = _parse_flag(row.get("hasstateowner", "")) if has_state else None
            # A single plot can appear multiple times (multiple owners /
            # multiple source files). Keep the largest plot valuation so
            # we expose the most conservative figure to the user, and
            # stick the KW/entities/flags from the winning row.
            prev = seen_per_plot.get(lot)
            if prev is None or value > prev[0]:
                seen_per_plot[lot] = (value, value_old, kw_val, entities_val, sluz, ten, state)
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
    for lot, (value, value_old, kw_val, entities_val, sluz, ten, state) in seen_per_plot.items():
        yield lot, value, value_old, kw_val, entities_val, sluz, ten, state


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
            insert_sql = (
                "INSERT INTO roszczenia"
                " (id_dzialki, wartosc_dzialki, wartosc_dzialki_old, kw, entities,"
                "  has_sluzebnosci, has_10_or_more_owners, has_state_owner)"
                " VALUES %s"
            )
            batch: list[Row] = []
            written = 0
            for r in read_rows(args.csv_path):
                batch.append(r)
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
