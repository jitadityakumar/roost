-- Real walking distance/duration (Google Routes API v2, travelMode=WALK)
-- from a listing's lat/lon (migration 0009) to each nearby station resolved
-- by app/commute/stations.py's resolve_crs_codes(). Computed once at scrape
-- time (see app/jobs/handlers.py::handle_rightmove_extract), never a live
-- call on page load -- rows are deleted and reinserted wholesale on every
-- recompute, not upserted individually.

CREATE TABLE station_walk_distances (
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    crs TEXT NOT NULL,
    distance_meters INTEGER,
    duration_seconds INTEGER,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (listing_id, crs)
);
