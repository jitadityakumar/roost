-- Persist Rightmove's propertyData.location.{latitude,longitude,pinType}
-- (issue #26). pinType is often 'APPROXIMATE_POINT' rather than exact --
-- kept alongside the coordinates so a future consumer can tell how much to
-- trust them. Usage beyond raw storage (map display, distance calcs) is
-- deliberately undecided; plain ALTER TABLE, no CHECK constraint involved.

ALTER TABLE listings ADD COLUMN latitude REAL;
ALTER TABLE listings ADD COLUMN longitude REAL;
ALTER TABLE listings ADD COLUMN pin_type TEXT;
