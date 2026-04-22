#!/usr/bin/env python3
"""Recompute cx_2180 / cy_2180 on transakcje_gruntowe from gruntomat.lots_enriched.

The sqlite dump we load from (transakcje_wszystkie.sqlite) ships
centroid_x / centroid_y in per-województwo local CRSes (PUWG 1965,
multiple PUWG 2000 zones, some with x/y swapped). They're useless for
cross-powiat distance queries. This script replaces them with EPSG:2180
centroids pulled from gruntomat.lots_enriched via id_dzialki match.

Flow:
  1. NULL out cx_2180 / cy_2180 / centroid_x / centroid_y on transakcje.
  2. Dump (id_dzialki, cx_2180, cy_2180) from gruntomat to a local TSV
     via COPY TO STDOUT.
  3. COPY the TSV into a temp table on transakcje DB.
  4. UPDATE transakcje_gruntowe SET cx_2180=, cy_2180= FROM temp JOIN
     on id_dzialki.
  5. DROP TEMP.

Idempotent. Needs GEO_DB_* (gruntomat) and TRANSAKCJE_DB_* envs.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import psycopg2

logger = logging.getLogger("refresh_centroids")

TSV_PATH = Path("/tmp/lot_centroids.tsv")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    gm = psycopg2.connect(
        host=os.environ["GEO_DB_HOST"],
        port=int(os.environ.get("GEO_DB_PORT", "5432")),
        dbname=os.environ["GEO_DB_NAME"],
        user=os.environ["GEO_DB_USER"],
        password=os.environ["GEO_DB_PASSWORD"],
        connect_timeout=30,
    )
    tx = psycopg2.connect(
        host=os.environ["TRANSAKCJE_DB_HOST"],
        port=int(os.environ.get("TRANSAKCJE_DB_PORT", "5432")),
        dbname=os.environ["TRANSAKCJE_DB_NAME"],
        user=os.environ["TRANSAKCJE_DB_USER"],
        password=os.environ["TRANSAKCJE_DB_PASSWORD"],
        connect_timeout=30,
    )

    try:
        # Step 1 — clear stale centroid cols on transakcje.
        logger.info("clearing junk centroid columns on transakcje_gruntowe…")
        t0 = time.time()
        with tx.cursor() as cur:
            cur.execute(
                "UPDATE transakcje_gruntowe "
                "SET cx_2180 = NULL, cy_2180 = NULL, "
                "    centroid_x = NULL, centroid_y = NULL "
                "WHERE cx_2180 IS NOT NULL OR cy_2180 IS NOT NULL "
                "   OR centroid_x IS NOT NULL OR centroid_y IS NOT NULL"
            )
            logger.info(
                "  cleared %d rows in %.0fs", cur.rowcount, time.time() - t0
            )
        tx.commit()

        # Step 2 — dump centroids from gruntomat to local TSV via COPY.
        logger.info("dumping gruntomat centroids → %s", TSV_PATH)
        t0 = time.time()
        # lots_enriched already has a precomputed ``centroid`` column in
        # EPSG:2180 — use it directly. Running ST_Centroid(geom) for 39M
        # rows takes ~90 hours; this takes minutes.
        with TSV_PATH.open("wb") as f, gm.cursor() as cur:
            cur.copy_expert(
                "COPY ("
                " SELECT id_dzialki,"
                "        ST_X(centroid),"
                "        ST_Y(centroid) "
                " FROM lots_enriched WHERE centroid IS NOT NULL"
                ") TO STDOUT WITH (FORMAT text)",
                f,
            )
        size_mb = TSV_PATH.stat().st_size / 1024 / 1024
        logger.info("  wrote %.1f MB in %.0fs", size_mb, time.time() - t0)

        # Step 3 — COPY the TSV into a temp table on transakcje DB.
        logger.info("creating lots_centroids temp table + loading…")
        t0 = time.time()
        with tx.cursor() as cur:
            cur.execute(
                "CREATE TEMP TABLE lots_centroids ("
                " id_dzialki TEXT PRIMARY KEY,"
                " cx DOUBLE PRECISION,"
                " cy DOUBLE PRECISION"
                ") ON COMMIT PRESERVE ROWS"
            )
            with TSV_PATH.open("rb") as f:
                # Temp might have duplicate id_dzialki across gruntomat
                # (rare, but ON CONFLICT DO NOTHING would be nicer —
                # COPY doesn't support it so we use a staging table).
                cur.execute("CREATE TEMP TABLE lots_stage ("
                            " id_dzialki TEXT,"
                            " cx DOUBLE PRECISION,"
                            " cy DOUBLE PRECISION"
                            ") ON COMMIT PRESERVE ROWS")
                cur.copy_expert(
                    "COPY lots_stage (id_dzialki, cx, cy) "
                    "FROM STDIN WITH (FORMAT text)",
                    f,
                )
            # Dedup into the final temp (keep any row per id_dzialki).
            cur.execute(
                "INSERT INTO lots_centroids (id_dzialki, cx, cy) "
                "SELECT id_dzialki, (ARRAY_AGG(cx))[1], (ARRAY_AGG(cy))[1] "
                "FROM lots_stage GROUP BY id_dzialki"
            )
            cur.execute("SELECT COUNT(*) FROM lots_centroids")
            logger.info(
                "  loaded %d unique centroids in %.0fs",
                cur.fetchone()[0], time.time() - t0,
            )

            # Step 4 — UPDATE transakcje with centroids.
            logger.info("updating transakcje_gruntowe from lots_centroids…")
            t0 = time.time()
            cur.execute(
                "UPDATE transakcje_gruntowe t "
                "SET cx_2180 = lc.cx, cy_2180 = lc.cy "
                "FROM lots_centroids lc "
                "WHERE t.id_dzialki = lc.id_dzialki"
            )
            logger.info(
                "  updated %d rows in %.0fs", cur.rowcount, time.time() - t0
            )
        tx.commit()

        # Step 5 — summary.
        with tx.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), "
                " COUNT(*) FILTER (WHERE cx_2180 IS NOT NULL) "
                "FROM transakcje_gruntowe"
            )
            total, with_c = cur.fetchone()
            logger.info(
                "final: total=%d  with_centroid=%d  (%.1f%%)",
                total, with_c, 100.0 * with_c / total if total else 0.0,
            )
    finally:
        tx.close()
        gm.close()
        if TSV_PATH.exists():
            try:
                TSV_PATH.unlink()
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
