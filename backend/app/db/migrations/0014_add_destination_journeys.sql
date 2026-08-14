-- Best train-journey-planner result per (listing, destination) -- computed
-- once at scrape time (app/jobs/handlers.py) or on manual recompute (see
-- app/destinations/compute.py), never a live call on page load. A listing's
-- rows are deleted and reinserted wholesale on each recompute, not upserted
-- individually -- same precedent as station_walk_distances (migration
-- 0011). A destination with no route found in any candidate origin simply
-- has no row here -- the frontend renders that as "no route found" rather
-- than treating an absent row as an error.

CREATE TABLE destination_journeys (
    listing_id        INTEGER NOT NULL REFERENCES listings(id),
    destination_id    INTEGER NOT NULL REFERENCES frequent_destinations(id),
    duration_minutes  INTEGER NOT NULL,
    kind              TEXT NOT NULL CHECK (kind IN ('direct', 'interchange')),
    num_changes       INTEGER NOT NULL,
    operator          TEXT,
    origin_crs        TEXT NOT NULL,
    origin_name       TEXT NOT NULL,
    departure_time    TEXT NOT NULL,
    arrival_time      TEXT NOT NULL,
    computed_at       TEXT NOT NULL,
    PRIMARY KEY (listing_id, destination_id)
);
