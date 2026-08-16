-- Home-vs-listing journey comparison (issue TBD): one journey per
-- destination from the user's own home lat/lon (ROOST_HOME_LAT/
-- ROOST_HOME_LON env vars, app/config.py -- deliberately not DB-stored so a
-- real home address never lands in the public repo or a shared DB dump).
-- Keyed by destination_id alone, not (listing_id, destination_id) like
-- destination_journeys -- home isn't a listing, it's a single fixed origin
-- shared across every listing's comparison. Recomputed by
-- compute_for_destination (app/destinations/compute.py) on every call, same
-- as the per-listing backfill, so a PATCH edit to day_of_week/time/
-- tfl_identifier is picked up correctly -- the admin UI just never exposes
-- editing those fields today (delete + recreate only), so in practice this
-- only ever runs once per destination's lifetime.
--
-- Only the fields needed for a live duration-diff are stored -- no
-- operator/origin_name/arrival_name/times, since the home journey itself is
-- never rendered, only diffed against a listing's own stored
-- duration_minutes at read time (routes/destination_journeys.py).

CREATE TABLE home_journeys (
    destination_id    INTEGER PRIMARY KEY REFERENCES frequent_destinations(id),
    duration_minutes  INTEGER NOT NULL,
    kind              TEXT NOT NULL CHECK (kind IN ('direct', 'interchange', 'multi_change')),
    num_changes       INTEGER NOT NULL,
    computed_at       TEXT NOT NULL
);
