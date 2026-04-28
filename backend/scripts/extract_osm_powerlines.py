"""Extract OSM power=line/minor_line/cable ways from planet_osm_ways into
osm_power_lines.

The gruntomat DB has osm2pgsql data in "middle" tables only — planet_osm_ways
(id, nodes bigint[], tags jsonb) and planet_osm_nodes (id, lat int, lon int,
tags jsonb). There is no planet_osm_line, so we reconstruct LineStrings by
joining ways against nodes and building the geometry with ST_MakeLine.

Nodes store lat/lon as integers scaled by 1e7 (the osm2pgsql internal format),
so we divide by 1e7 before ST_MakePoint and then ST_Transform from 4326 to
EPSG:2180.

Idempotent: TRUNCATEs osm_power_lines before inserting.

Usage:
    python backend/scripts/extract_osm_powerlines.py
"""

from __future__ import annotations

import logging
import os
import sys

import psycopg2

logger = logging.getLogger("extract_osm_powerlines")

DB_HOST = os.environ.get("GEO_DB_HOST", "145.239.2.73")
DB_PORT = int(os.environ.get("GEO_DB_PORT", "5432"))
DB_NAME = os.environ.get("GEO_DB_NAME", "gruntomat_geo")
DB_USER = os.environ.get("GEO_DB_USER", "gruntomat")
DB_PASSWORD = os.environ.get("GEO_DB_PASSWORD", "gruntomat_dev")


# Voltage parser: OSM 'voltage' can be '110000', '110 kV', '110000;15000',
# '230/400', 'medium', etc. The OSM convention for the `voltage` key is that
# the value is in volts, so we simply extract the first integer in the string
# and keep it as-is. Values that aren't numeric (e.g. 'medium') become NULL.
VOLTAGE_PARSE_SQL = r"""
    CASE
        WHEN w.tags ? 'voltage' THEN
            NULLIF(
                (regexp_match(w.tags->>'voltage', '([0-9]+(?:\.[0-9]+)?)'))[1],
                ''
            )::numeric
        ELSE NULL
    END
"""


EXTRACT_SQL = f"""
WITH power_ways AS (
    SELECT
        w.id,
        w.tags->>'power'    AS power_type,
        w.tags->>'voltage'  AS voltage_raw,
        {VOLTAGE_PARSE_SQL} AS voltage,
        NULLIF(
            (regexp_match(COALESCE(w.tags->>'cables', ''), '([0-9]+)'))[1],
            ''
        )::int AS cables,
        w.tags->>'operator' AS operator,
        w.tags->>'name'     AS name,
        w.nodes
    FROM planet_osm_ways w
    WHERE w.tags ? 'power'
      AND w.tags->>'power' IN ('line', 'minor_line', 'cable')
      AND array_length(w.nodes, 1) >= 2
),
-- Explode each way into its ordered list of nodes
exploded AS (
    SELECT
        pw.id,
        ord,
        node_id
    FROM power_ways pw
    CROSS JOIN LATERAL unnest(pw.nodes) WITH ORDINALITY AS u(node_id, ord)
),
-- Join node coordinates. lat/lon are int*1e7 in the osm2pgsql middle.
points AS (
    SELECT
        e.id,
        e.ord,
        ST_SetSRID(
            ST_MakePoint(n.lon / 1e7, n.lat / 1e7),
            4326
        ) AS pt
    FROM exploded e
    JOIN planet_osm_nodes n ON n.id = e.node_id
),
-- Reassemble into LineString in EPSG:2180. ST_MakeLine(ARRAY) keeps order.
lines AS (
    SELECT
        id,
        ST_Transform(
            ST_MakeLine(array_agg(pt ORDER BY ord)),
            2180
        ) AS geom,
        COUNT(*) AS n_points
    FROM points
    GROUP BY id
)
INSERT INTO osm_power_lines
    (osm_id, power_type, voltage, voltage_raw, cables, operator, name, geom)
SELECT
    l.id,
    pw.power_type,
    pw.voltage,
    pw.voltage_raw,
    pw.cables,
    pw.operator,
    pw.name,
    l.geom
FROM lines l
JOIN power_ways pw ON pw.id = l.id
WHERE l.n_points >= 2
  AND ST_NumPoints(l.geom) >= 2
  AND NOT ST_IsEmpty(l.geom)
ON CONFLICT (osm_id) DO UPDATE SET
    power_type  = EXCLUDED.power_type,
    voltage     = EXCLUDED.voltage,
    voltage_raw = EXCLUDED.voltage_raw,
    cables      = EXCLUDED.cables,
    operator    = EXCLUDED.operator,
    name        = EXCLUDED.name,
    geom        = EXCLUDED.geom;
"""


def db_connect():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=15,
    )


def run() -> int:
    logger.info("Connecting to %s@%s/%s", DB_USER, DB_HOST, DB_NAME)
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            logger.info("TRUNCATE osm_power_lines")
            cur.execute("TRUNCATE TABLE osm_power_lines RESTART IDENTITY")

            logger.info("Extracting power=line|minor_line|cable from planet_osm_ways …")
            cur.execute(EXTRACT_SQL)

            cur.execute("SELECT COUNT(*) FROM osm_power_lines")
            total = cur.fetchone()[0]
            logger.info("Inserted %d rows into osm_power_lines", total)

            cur.execute(
                "SELECT power_type, COUNT(*) FROM osm_power_lines"
                " GROUP BY power_type ORDER BY 2 DESC"
            )
            for pt, n in cur.fetchall():
                logger.info("  %-12s %d", pt, n)

            cur.execute(
                "SELECT COUNT(*) FROM osm_power_lines WHERE voltage IS NOT NULL"
            )
            with_v = cur.fetchone()[0]
            logger.info("  with voltage: %d", with_v)
        conn.commit()
    finally:
        conn.close()
    return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    sys.exit(run())


if __name__ == "__main__":
    main()
