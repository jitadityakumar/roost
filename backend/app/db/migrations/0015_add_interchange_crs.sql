-- CRS code of the interchange station for a single-change journey (null for
-- a direct journey) -- lets the UI show "1 change (via CLJ)" instead of the
-- less useful "via <origin station>" it originally showed. train-journey-
-- planner's /api/journeys only ever returns 0 or 1 changes today
-- (InterchangeTripOut.interchange: StationOut), so this is a single CRS
-- code, not a list -- see app/destinations/compute.py.

ALTER TABLE destination_journeys ADD COLUMN interchange_crs TEXT;
