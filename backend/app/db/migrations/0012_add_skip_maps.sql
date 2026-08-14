-- Lets a rightmove_extract job opt out of the Google Maps walking-distance
-- computation (app/jobs/handlers.py::_compute_station_walk_distances).
-- Needed for POST /refresh?skip_maps=true, used by
-- scripts/backfill-rightmove.sh --skip-maps to bulk re-scrape without
-- making real, billed Google Routes API calls for every listing.

ALTER TABLE jobs ADD COLUMN skip_maps INTEGER NOT NULL DEFAULT 0;
