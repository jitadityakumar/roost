-- Drop the unused `commute_data` table. The commute-station join (Phase 2)
-- was designed to fetch journey times live from london-commuter-stations'
-- API on each listing-detail page load rather than persist them -- there's
-- no manual-edit stickiness concern and no benefit to caching a ~30ms
-- same-host call, so nothing was ever going to populate this table under
-- that design. Name->CRS resolution is likewise a static in-process lookup,
-- not stored.
--
-- Nothing references commute_data as a parent, only the reverse (it holds a
-- REFERENCES listings(id)), so this drops cleanly with foreign_keys left on
-- -- no PRAGMA toggle/table-rebuild dance needed, unlike 0002/0004.

DROP INDEX IF EXISTS idx_commute_data_listing_id;
DROP TABLE IF EXISTS commute_data;
