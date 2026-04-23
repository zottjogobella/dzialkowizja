#!/usr/bin/env python3
"""Wire up postgres_fdw on the transakcje DB so it can JOIN gruntomat.public.lots_enriched natively.

Idempotent. Creates (or replaces):
  * extension postgres_fdw
  * server    gruntomat_fdw   → GEO_DB_* host
  * user mapping for the current transakcje user
  * foreign table ``lots_enriched`` imported from gruntomat.public.lots_enriched

After this, queries like::

    SELECT t.*, ST_Distance(le.centroid, :pt) AS d
    FROM transakcje_gruntowe t
    JOIN lots_enriched le USING (id_dzialki)
    WHERE ST_DWithin(le.centroid, :pt, 10000)
    ORDER BY d
    LIMIT 30

work directly — postgres_fdw pushes ST_DWithin / the centroid GiST index
down to gruntomat so the spatial filter runs on the 39M-row side.

Needs superuser on transakcje DB for CREATE EXTENSION the first time.
"""
from __future__ import annotations

import logging
import os
import sys

import psycopg2
from psycopg2 import sql

logger = logging.getLogger("setup_fdw")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    geo_host = os.environ["GEO_DB_HOST"]
    geo_port = os.environ.get("GEO_DB_PORT", "5432")
    geo_name = os.environ["GEO_DB_NAME"]
    geo_user = os.environ["GEO_DB_USER"]
    geo_pw = os.environ["GEO_DB_PASSWORD"]

    conn = psycopg2.connect(
        host=os.environ["TRANSAKCJE_DB_HOST"],
        port=int(os.environ.get("TRANSAKCJE_DB_PORT", "5432")),
        dbname=os.environ["TRANSAKCJE_DB_NAME"],
        user=os.environ["TRANSAKCJE_DB_USER"],
        password=os.environ["TRANSAKCJE_DB_PASSWORD"],
        connect_timeout=30,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            logger.info("CREATE EXTENSION postgres_fdw…")
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgres_fdw")

            # Drop + recreate server + user mapping + foreign table — easier
            # than patching in place across every option, and this runs in
            # <1s so it's fine to rebuild on every invocation.
            logger.info("dropping stale FDW objects if present…")
            cur.execute("DROP FOREIGN TABLE IF EXISTS lots_enriched CASCADE")
            cur.execute("DROP USER MAPPING IF EXISTS FOR CURRENT_USER SERVER gruntomat_fdw")
            cur.execute("DROP SERVER IF EXISTS gruntomat_fdw CASCADE")

            logger.info("creating server gruntomat_fdw → %s:%s/%s", geo_host, geo_port, geo_name)
            cur.execute(
                sql.SQL(
                    "CREATE SERVER gruntomat_fdw FOREIGN DATA WRAPPER postgres_fdw "
                    "OPTIONS (host {h}, port {p}, dbname {d}, fetch_size {f})"
                ).format(
                    h=sql.Literal(geo_host),
                    p=sql.Literal(geo_port),
                    d=sql.Literal(geo_name),
                    f=sql.Literal("10000"),
                )
            )

            logger.info("creating user mapping → %s@gruntomat", geo_user)
            cur.execute(
                sql.SQL(
                    "CREATE USER MAPPING FOR CURRENT_USER SERVER gruntomat_fdw "
                    "OPTIONS (user {u}, password {w})"
                ).format(u=sql.Literal(geo_user), w=sql.Literal(geo_pw))
            )

            logger.info("importing foreign schema…")
            cur.execute(
                "IMPORT FOREIGN SCHEMA public LIMIT TO (lots_enriched) "
                "FROM SERVER gruntomat_fdw INTO public"
            )

            # Smoke test: simple count with a DWithin ring around Kraków.
            logger.info("smoke test — DWithin ring around Kraków centroid…")
            cur.execute(
                "SELECT COUNT(*) FROM lots_enriched "
                "WHERE centroid IS NOT NULL "
                "  AND ST_DWithin(centroid, "
                "                 ST_SetSRID(ST_MakePoint(566230, 241097), 2180), "
                "                 2000)"
            )
            logger.info("  count=%d", cur.fetchone()[0])

            # Join smoke test — the real thing we care about.
            logger.info("smoke test — JOIN transakcje × lots_enriched in 1 km…")
            cur.execute(
                "SELECT COUNT(*) FROM transakcje_gruntowe t "
                "JOIN lots_enriched le USING (id_dzialki) "
                "WHERE le.centroid IS NOT NULL "
                "  AND ST_DWithin(le.centroid, "
                "                 ST_SetSRID(ST_MakePoint(566230, 241097), 2180), "
                "                 1000)"
            )
            logger.info("  count=%d", cur.fetchone()[0])
    finally:
        conn.close()
    logger.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
