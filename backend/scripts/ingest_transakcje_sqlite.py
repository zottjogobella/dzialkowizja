#!/usr/bin/env python3
"""Replace the transakcje Postgres DB contents from a corrected sqlite dump.

Source sqlite has the same schema as the live ``transakcje_gruntowe`` table
plus one new column (``do_wyceny_rozszerzone``) and with outlier / do_wyceny
/ jakosc_ceny / segment_rynku flags populated by the upstream RCN cleanup.

Flow:
  1. Ensure the destination column ``do_wyceny_rozszerzone`` exists on
     ``transakcje_gruntowe`` (add if missing). All other flag columns
     (jakosc_ceny, segment_rynku, do_wyceny, outlier, powierzchnia_m2_rcn,
     powierzchnia_nieruchomosci_m2, cx_2180, cy_2180) already live on prod.
  2. TRUNCATE transakcje_gruntowe.
  3. Stream rows from sqlite and bulk-insert using COPY — ~10.8M rows.

Usage::

    TRANSAKCJE_DB_HOST=... TRANSAKCJE_DB_USER=... TRANSAKCJE_DB_PASSWORD=... \
    python ingest_transakcje_sqlite.py /path/to/transakcje_wszystkie.sqlite
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

import psycopg2

logger = logging.getLogger("ingest_transakcje")

# Columns copied sqlite → postgres, in the exact order we stream / COPY.
# Keep this in sync with the sqlite schema (see data/ inspection). ``id``
# is omitted — Postgres has a sequence we don't want to reuse.
COLUMNS = [
    "teryt", "wojewodztwo", "transakcja_gml_id", "id_dzialki",
    "data_transakcji", "rok", "oznaczenie_dokumentu", "tworca_dokumentu",
    "cena_transakcji", "cena_nieruchomosci", "cena_dzialki", "cena_do_analizy",
    "kwota_vat", "liczba_dzialek_w_transakcji", "powierzchnia_m2",
    "powierzchnia_nieruchomosci_ha", "cena_za_m2", "rodzaj_nieruchomosci",
    "rodzaj_rynku", "rodzaj_transakcji", "rodzaj_prawa", "udzial_w_prawie",
    "sposob_uzytkowania", "przeznaczenie_mpzp", "strona_kupujaca",
    "strona_sprzedajaca", "miejscowosc", "ulica", "numer_porzadkowy",
    "geometria_wkt", "centroid_x", "centroid_y", "dodatkowe_informacje",
    "ma_cene_dzialki", "jedna_dzialka", "jakosc_ceny", "segment_rynku",
    "powierzchnia_nieruchomosci_m2", "powierzchnia_m2_rcn", "do_wyceny",
    "outlier", "do_wyceny_rozszerzone",
]

# Chunk size for streaming sqlite → postgres COPY buffer.
CHUNK_ROWS = 50_000


def _escape_copy(v) -> str:
    """Serialize one sqlite value for a Postgres COPY text stream."""
    if v is None:
        return r"\N"
    if isinstance(v, (int, float)):
        return repr(v)
    # Text: escape backslash, tab, newline, carriage return.
    s = str(v)
    return (
        s.replace("\\", "\\\\")
         .replace("\t", "\\t")
         .replace("\n", "\\n")
         .replace("\r", "\\r")
    )


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='transakcje_gruntowe'
            """
        )
        present = {r[0] for r in cur.fetchall()}
        missing = [c for c in COLUMNS if c not in present]
        if missing:
            logger.warning("columns missing in postgres: %s", missing)
            # Only add ones we know the type for.
            if "do_wyceny_rozszerzone" in missing:
                logger.info("adding column do_wyceny_rozszerzone")
                cur.execute(
                    "ALTER TABLE transakcje_gruntowe "
                    "ADD COLUMN do_wyceny_rozszerzone INTEGER NOT NULL DEFAULT 0"
                )
        # cx_2180 / cy_2180 live on prod but not on sqlite — we don't touch
        # them (they come from a separate pipeline that recomputes centroids
        # in EPSG:2180 from geometria_wkt after ingest).
    conn.commit()


def stream_copy(sq, pg, total: int, skip_geometry: bool) -> int:
    """Stream rows from sqlite into postgres via COPY FROM STDIN."""
    # sqlite SELECT in the same column order as COPY target.
    cols_sql = ", ".join(COLUMNS)
    sq_cur = sq.cursor()
    sq_cur.execute(f"SELECT {cols_sql} FROM transakcje_gruntowe")

    pg_cur = pg.cursor()
    pg_cur.execute("TRUNCATE transakcje_gruntowe")
    # Trigger COPY with text format. Buffer a chunk, send, repeat. This is
    # ~5-10× faster than execute_batch / executemany for 10M+ rows.
    done = 0
    t0 = time.time()
    while True:
        rows = sq_cur.fetchmany(CHUNK_ROWS)
        if not rows:
            break
        buf = io.StringIO()
        for row in rows:
            if skip_geometry:
                # Blank out geometria_wkt (index 29 in COLUMNS) — too large to
                # ship round-trip if user chose --skip-geometry. Not our case
                # today but leave the knob.
                row = list(row)
                row[29] = None
            buf.write("\t".join(_escape_copy(v) for v in row))
            buf.write("\n")
        buf.seek(0)
        pg_cur.copy_expert(
            f"COPY transakcje_gruntowe ({cols_sql}) FROM STDIN WITH (FORMAT text)",
            buf,
        )
        done += len(rows)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        logger.info(
            "  %d / %d rows  (%.0f rows/s, %.0fs elapsed)",
            done, total, rate, elapsed,
        )
    pg.commit()
    return done


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlite_path", type=Path)
    ap.add_argument(
        "--skip-geometry", action="store_true",
        help="Don't ship geometria_wkt (debug / bandwidth knob)",
    )
    args = ap.parse_args(argv)

    if not args.sqlite_path.exists():
        logger.error("sqlite not found: %s", args.sqlite_path)
        return 1

    # Open read-only so the source file (often a bind-mounted :ro volume)
    # isn't touched. The file: URI form avoids sqlite's journal write.
    sq = sqlite3.connect(f"file:{args.sqlite_path}?mode=ro", uri=True)
    total = sq.execute("SELECT COUNT(*) FROM transakcje_gruntowe").fetchone()[0]
    logger.info("sqlite rows: %d", total)

    pg_kw = {
        "host": os.environ["TRANSAKCJE_DB_HOST"],
        "port": int(os.environ.get("TRANSAKCJE_DB_PORT", "5432")),
        "dbname": os.environ["TRANSAKCJE_DB_NAME"],
        "user": os.environ["TRANSAKCJE_DB_USER"],
        "password": os.environ["TRANSAKCJE_DB_PASSWORD"],
        "connect_timeout": 30,
    }
    logger.info("connecting to %s:%s/%s", pg_kw["host"], pg_kw["port"], pg_kw["dbname"])
    pg = psycopg2.connect(**pg_kw)
    try:
        ensure_schema(pg)
        n = stream_copy(sq, pg, total, args.skip_geometry)
        logger.info("inserted %d rows", n)
        # Rebuild centroid columns used by the nearest-transactions query.
        logger.info("recomputing cx_2180 / cy_2180 from centroid_x / centroid_y")
        with pg.cursor() as cur:
            # Prod stores centroids in EPSG:2180 as cx/cy_2180. Sqlite ships
            # centroid_x / centroid_y in the same CRS already, so just copy.
            cur.execute(
                "UPDATE transakcje_gruntowe SET "
                " cx_2180 = centroid_x, cy_2180 = centroid_y "
                "WHERE centroid_x IS NOT NULL AND centroid_y IS NOT NULL"
            )
            logger.info("  updated %d rows with centroid coords", cur.rowcount)
        pg.commit()
    finally:
        pg.close()
        sq.close()
    logger.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
