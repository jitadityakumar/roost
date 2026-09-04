-- Issue #76: adds lat/lon to station_walk_distances so a Google Maps
-- walking link can be built for every Nearest Stations entry, not just the
-- CRS-resolved national-rail stations the Commute section covers.
-- resolve_stop_point() already gets a lat/lon for every resolved TfL
-- StopPoint (used internally for haversine gap-scoring, then discarded --
-- see tfl_client.py) -- this just persists it alongside stop_point_id
-- rather than re-resolving it live on every render.
--
-- Plain ALTER TABLE ADD COLUMN: station_walk_distances has no CHECK
-- constraint and nothing else has a foreign key into it, so the
-- rebuild-and-swap dance other migrations need (self-referencing FK,
-- CHECK constraint changes) doesn't apply here -- same reasoning as
-- 0023's council_tax_rates table.
--
-- Existing rows keep lat=NULL/lon=NULL until their next recompute
-- (POST /{listing_id}/walk-refresh, or the next Rightmove re-scrape) --
-- no backfill needed at the schema level, same precedent as 0018.
ALTER TABLE station_walk_distances ADD COLUMN lat REAL;
ALTER TABLE station_walk_distances ADD COLUMN lon REAL;
