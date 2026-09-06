-- Lets the admin pick one crime baseline (e.g. "Barnes") as the fixed
-- reference point for the crime-comparison bar chart, always rendered at
-- 1.0x, with the listing and every other baseline shown relative to it
-- (instead of the listing itself being the 1.0x base). Issue #84.

ALTER TABLE crime_baselines ADD COLUMN is_reference INTEGER NOT NULL DEFAULT 0 CHECK (is_reference IN (0, 1));
