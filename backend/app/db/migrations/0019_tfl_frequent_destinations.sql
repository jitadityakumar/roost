-- Issue #47: replace train-journey-planner (GTFS, national-rail-only) with
-- TfL's Unified Journey Planner API as the sole path for Frequent
-- Destinations -- full replacement, not a fallback. See that issue's plan
-- comment (and its three addenda) for the full rationale.
--
-- frequent_destinations gains destination_type/tfl_identifier and drops
-- crs -- a destination is now either a "station" (identified by a TfL
-- StopPoint id, which unlike a CRS code can address Tube/DLR/Overground/
-- tram-only stations) or a "postcode" (TfL's `to` param accepts a raw UK
-- postcode directly, no resolution step). tfl_identifier is nullable at the
-- DB level -- there is no valid TfL identifier to derive from the old crs
-- column, so existing rows would get NULL here and must be re-picked
-- through the admin form before they resolve again. In this deployment
-- there are zero existing rows (all frequent destinations were deleted
-- ahead of this migration, to be re-added through the new form), so that
-- re-pick step doesn't apply, but the column stays nullable regardless --
-- app/destinations/compute.py must treat a NULL tfl_identifier as
-- "unresolvable, skip" the same way it already treats a missing origin.
--
-- destination_journeys.origin_crs/origin_name are repurposed (not
-- schema-changed) to hold the first non-walking leg's StopPoint id/name
-- instead of a rail CRS code/name -- see compute.py. destination_journeys
-- gains arrival_name (last non-walking leg's commonName, display-only, same
-- "descriptive, not used for lookup" precedent as origin_name) -- needed so
-- a postcode-type destination's resolved arrival station has something to
-- render (`origin_name` -> `arrival_name`), since interchange_crs
-- deliberately only ever covers non-final change stations.
--
-- SQLite has no ALTER TABLE ... DROP COLUMN / MODIFY CONSTRAINT, so
-- frequent_destinations goes through the standard rebuild-and-swap pattern
-- (see 0016/0017). destination_journeys has a live FK into
-- frequent_destinations (app/db/connection.py sets PRAGMA foreign_keys=ON),
-- so -- same as 0017's jobs rebuild -- foreign_keys must be off for the
-- DROP TABLE frequent_destinations below even though frequent_destinations
-- itself isn't self-referencing; a live FK *from* another table blocks the
-- drop the same way. Restored at the end; PRAGMA foreign_keys can't be
-- toggled inside a transaction, and this script runs outside one
-- (executescript(), not atomic -- a crash partway through leaves
-- frequent_destinations_new on disk with schema_version not yet bumped, and
-- the next boot retries this file from the top. The DROP IF EXISTS below
-- makes that retry safe, same precedent as every rebuild-and-swap migration
-- since 0002).

PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS frequent_destinations_new;

CREATE TABLE frequent_destinations_new (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    destination_type TEXT NOT NULL DEFAULT 'station' CHECK (destination_type IN ('station', 'postcode')),
    tfl_identifier   TEXT,
    station_name     TEXT NOT NULL,
    day_of_week      INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    time             TEXT NOT NULL,
    enabled          INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at       TEXT NOT NULL
);

INSERT INTO frequent_destinations_new (id, name, destination_type, tfl_identifier, station_name, day_of_week, time, enabled, created_at)
SELECT id, name, 'station', NULL, station_name, day_of_week, time, enabled, created_at
FROM frequent_destinations;

DROP TABLE frequent_destinations;

ALTER TABLE frequent_destinations_new RENAME TO frequent_destinations;

PRAGMA foreign_keys=ON;

ALTER TABLE destination_journeys ADD COLUMN arrival_name TEXT;
