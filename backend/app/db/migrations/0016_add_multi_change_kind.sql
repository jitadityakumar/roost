-- Widens destination_journeys.kind's CHECK constraint to allow
-- 'multi_change' -- train-journey-planner's OTP-sidecar-backed 2-5 change
-- fallback tier (GitHub issue #26 there), now used by
-- app/destinations/compute.py as a second-stage fallback per its own
-- documented two-step call contract: call /api/journeys first, only call
-- /api/journeys/multi-change if that came back empty. interchange_crs is
-- reused (not renamed) to hold a comma-joined list of every change
-- station's CRS code for a multi_change journey, not just a single code --
-- see compute.py::_interchange_crs.
--
-- SQLite has no ALTER TABLE ... DROP/MODIFY CONSTRAINT, so the CHECK is
-- widened via the standard rebuild-and-swap pattern: new table, copy rows,
-- drop old, rename. migrate.py's executescript() isn't atomic -- each
-- statement autocommits -- so a crash partway through this file (disk
-- full, OOM-kill) can leave destination_journeys_new on disk with
-- schema_version not yet bumped, and the next boot retries this file from
-- the top. The DROP IF EXISTS below makes that retry safe instead of
-- failing on "table destination_journeys_new already exists" -- same
-- precedent as 0002_status_rework.sql/0004_status_triage_approved_rejected.sql.

DROP TABLE IF EXISTS destination_journeys_new;

CREATE TABLE destination_journeys_new (
    listing_id        INTEGER NOT NULL REFERENCES listings(id),
    destination_id    INTEGER NOT NULL REFERENCES frequent_destinations(id),
    duration_minutes  INTEGER NOT NULL,
    kind              TEXT NOT NULL CHECK (kind IN ('direct', 'interchange', 'multi_change')),
    num_changes       INTEGER NOT NULL,
    operator          TEXT,
    origin_crs        TEXT NOT NULL,
    origin_name       TEXT NOT NULL,
    departure_time    TEXT NOT NULL,
    arrival_time      TEXT NOT NULL,
    computed_at       TEXT NOT NULL,
    interchange_crs   TEXT,
    PRIMARY KEY (listing_id, destination_id)
);

INSERT INTO destination_journeys_new SELECT * FROM destination_journeys;

DROP TABLE destination_journeys;

ALTER TABLE destination_journeys_new RENAME TO destination_journeys;
