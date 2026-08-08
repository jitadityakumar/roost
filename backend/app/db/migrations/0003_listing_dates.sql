-- Two new date fields (issue #11): Rightmove's own "added on" date for the
-- listing, and a dedicated "fetched on" timestamp for when *we* last
-- successfully ran rightmove_extract. Both are plain text/nullable columns
-- with no CHECK constraint, so a simple ALTER TABLE suffices -- no need for
-- the full table-rebuild dance 0002 used for its CHECK-constraint change.
--
-- rightmove_fetched_at is deliberately separate from updated_at: that column
-- is bumped by unrelated writes too (user_status toggles, manual edits,
-- extraction_status changes -- see store.py), so it isn't a clean proxy for
-- "when did we last scrape this listing." rightmove_fetched_at is only ever
-- written by handle_rightmove_extract.

ALTER TABLE listings ADD COLUMN listing_added_on TEXT;
ALTER TABLE listings ADD COLUMN rightmove_fetched_at TEXT;
