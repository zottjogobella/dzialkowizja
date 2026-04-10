-- powerlines schema for BDOT10k + OSM electric line data.
--
-- Target DB: gruntomat (PostGIS, 145.239.2.73:5432). These tables are NOT part
-- of the app's own Alembic-managed database — they live alongside lots_enriched
-- so the powerlines endpoint can do spatial joins against plots directly.
--
-- Apply with:
--   PGPASSWORD=gruntomat_dev psql -h 145.239.2.73 -U gruntomat -d gruntomat \
--       -f backend/scripts/powerlines_schema.sql
--
-- Sources:
--   - BDOT10k OT_SULN_L (linie elektroenergetyczne) — GML per-powiat from
--     https://opendata.geoportal.gov.pl/bdot10k/schemat2021/{woj}/{teryt}_GML.zip
--     Ingested by backend/scripts/ingest_bdot_powerlines.py
--   - OSM power=line/minor_line/cable extracted from planet_osm_ways +
--     planet_osm_nodes by backend/scripts/extract_osm_powerlines.py

CREATE TABLE IF NOT EXISTS bdot_power_lines (
    id              SERIAL PRIMARY KEY,
    gml_id          TEXT UNIQUE,         -- OT_SULN_L gml:id (globally unique in BDOT10k)
    lokalny_id      TEXT,                -- ot:lokalnyId (matches gml_id minus 'id_' prefix)
    rodzaj          TEXT,                -- raw 'rodzaj' from GML
                                         --   'linia elektroenergetyczna najwyższego napięcia'
                                         --   'linia elektroenergetyczna wysokiego napięcia'
                                         --   'linia elektroenergetyczna średniego napięcia'
                                         --   'linia elektroenergetyczna niskiego napięcia'
    napiecie_klasa  TEXT,                -- derived: 'najwyzsze'|'wysokie'|'srednie'|'niskie'
    source_woj      CHAR(2),             -- TERYT województwa skąd pochodzi (02..32)
    source_powiat   CHAR(4),             -- TERYT powiatu
    wersja          TIMESTAMP,           -- ot:wersja
    geom            GEOMETRY(LineString, 2180)
);

CREATE INDEX IF NOT EXISTS bdot_power_lines_geom_idx    ON bdot_power_lines USING GIST (geom);
CREATE INDEX IF NOT EXISTS bdot_power_lines_woj_idx     ON bdot_power_lines (source_woj);
CREATE INDEX IF NOT EXISTS bdot_power_lines_powiat_idx  ON bdot_power_lines (source_powiat);
CREATE INDEX IF NOT EXISTS bdot_power_lines_klasa_idx   ON bdot_power_lines (napiecie_klasa);


CREATE TABLE IF NOT EXISTS osm_power_lines (
    id              SERIAL PRIMARY KEY,
    osm_id          BIGINT UNIQUE,       -- planet_osm_ways.id
    power_type      TEXT,                -- line | minor_line | cable
    voltage         NUMERIC,             -- parsed first voltage value (volts) from tag 'voltage'
    voltage_raw     TEXT,                -- original 'voltage' tag value (for debugging)
    cables          INTEGER,             -- tag 'cables' if present
    operator        TEXT,                -- tag 'operator' if present
    name            TEXT,                -- tag 'name' if present
    geom            GEOMETRY(LineString, 2180)
);

CREATE INDEX IF NOT EXISTS osm_power_lines_geom_idx    ON osm_power_lines USING GIST (geom);
CREATE INDEX IF NOT EXISTS osm_power_lines_type_idx    ON osm_power_lines (power_type);
CREATE INDEX IF NOT EXISTS osm_power_lines_voltage_idx ON osm_power_lines (voltage);


-- Point / polygon electric devices from BDOT10k.
--
-- Sources (all filtered to electro-only 'rodzaj' values):
--   OT_BUWT_P — słup energetyczny (transmission pylons / poles) — Point
--   OT_BUIT_P — transformator, zespół transformatorów (transformer stations) — Point
--   OT_BUIT_A — zespół transformatorów — Polygon
--   OT_KUPG_P — podstacja elektroenergetyczna, elektrownia — Point
--   OT_KUPG_A — podstacja elektroenergetyczna, elektrownia, elektrociepłownia — Polygon
--
-- Geometry column is GEOMETRY (not Point or Polygon) because we keep both.
-- Ingested by backend/scripts/ingest_bdot_power_devices.py
CREATE TABLE IF NOT EXISTS bdot_power_devices (
    id              SERIAL PRIMARY KEY,
    gml_id          TEXT UNIQUE,
    lokalny_id      TEXT,
    source_class    TEXT,                -- OT_BUWT_P | OT_BUIT_P | OT_BUIT_A | OT_KUPG_P | OT_KUPG_A
    rodzaj          TEXT,                -- raw 'rodzaj' value from BDOT
    kategoria       TEXT,                -- derived: slup | transformator | podstacja | elektrownia | inne
    source_woj      CHAR(2),
    source_powiat   CHAR(4),
    wersja          TIMESTAMP,
    geom            GEOMETRY(Geometry, 2180)
);

CREATE INDEX IF NOT EXISTS bdot_power_devices_geom_idx      ON bdot_power_devices USING GIST (geom);
CREATE INDEX IF NOT EXISTS bdot_power_devices_woj_idx       ON bdot_power_devices (source_woj);
CREATE INDEX IF NOT EXISTS bdot_power_devices_powiat_idx    ON bdot_power_devices (source_powiat);
CREATE INDEX IF NOT EXISTS bdot_power_devices_kategoria_idx ON bdot_power_devices (kategoria);
