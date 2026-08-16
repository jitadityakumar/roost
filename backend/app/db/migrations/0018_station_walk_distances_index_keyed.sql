-- Issue #40 PR2: drops the 1mi/national-rail-only scope from station walk
-- distance computation, extending it to tube/tram/DLR/overground at any
-- distance. The old table was CRS-keyed, which only ever worked because
-- the old flow exclusively covered national-rail stations resolvable
-- against stations.csv -- tube/tram/DLR/overground stations have no CRS
-- code at all, so the key must change.
--
-- New key: (listing_id, station_index), station_index being the entry's
-- position in Rightmove's own nearest_stations_raw list at compute time.
-- nearest_stations_raw is always fully replaced (not merged) on every
-- scrape, so positional keying is stable within one scrape and needs no
-- name-matching step to re-attach a row at render time. rightmove_name is
-- stored alongside so readers can verify a row still matches the station
-- currently at that index before attaching it (guards against Rightmove
-- reordering its nearest-3 between scrapes without walk data being
-- recomputed in lockstep -- see app/commute/walk_store.py::lookup_walk).
--
-- No data-preservation need -- every listing's walk data gets recomputed on
-- its next scrape/backfill regardless. Plain DROP/CREATE (not the
-- rebuild-and-swap pattern used for jobs/listings elsewhere) since nothing
-- else has a foreign key into this table and it has none of its own that's
-- self-referencing.

DROP TABLE IF EXISTS station_walk_distances;

CREATE TABLE station_walk_distances (
    listing_id      INTEGER NOT NULL REFERENCES listings(id),
    station_index   INTEGER NOT NULL,
    rightmove_name  TEXT NOT NULL,
    mode            TEXT,
    stop_point_id   TEXT,
    distance_meters INTEGER,
    duration_seconds INTEGER,
    computed_at     TEXT NOT NULL,
    PRIMARY KEY (listing_id, station_index)
);
