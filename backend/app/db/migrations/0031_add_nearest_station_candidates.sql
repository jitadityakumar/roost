-- Issue #92: Nearest Stations candidates discovered via TfL's /StopPoint
-- lat/lon/radius search, independent of Rightmove's own (often incomplete)
-- 3-station list -- see the issue's implementation plan comment for the
-- full design.
--
-- Keyed by (listing_id, stop_point_id), where stop_point_id is the
-- canonical (post-dedup) TfL StopPoint id for one physical station -- a
-- stable TfL identifier, unlike Rightmove's reorderable nearest_stations_raw
-- (station_walk_distances' index-keying + staleness guard has no analogue
-- needed here). Rows are wholesale deleted + reinserted per listing on each
-- recompute (store.replace_candidates), same precedent as
-- walk_store.replace_walk_distances.
--
-- Plain CREATE TABLE: no CHECK constraint, no self-referencing/FK-referenced
-- complications like migration 0017's rebuild-and-swap gotcha.
--
-- distance_meters is straight-line (from the radius search); walk_distance_
-- meters is the real routed walking-path distance (from the same TfL
-- Journey Planner call that produces duration_seconds, same as
-- station_walk_distances.distance_meters) -- kept as two separate columns
-- since they're never the same number and the frontend needs both (the
-- straight-line figure for the "as the crow flies" badge, the routed one
-- alongside the walk duration, matching station_walk_distances' precedent).
CREATE TABLE nearest_station_candidates (
    listing_id          INTEGER NOT NULL REFERENCES listings(id),
    stop_point_id       TEXT NOT NULL,
    name                TEXT NOT NULL,
    modes               TEXT NOT NULL,
    lat                 REAL,
    lon                 REAL,
    distance_meters     INTEGER NOT NULL,
    walk_distance_meters INTEGER,
    duration_seconds    INTEGER,
    computed_at         TEXT NOT NULL,
    PRIMARY KEY (listing_id, stop_point_id)
);
