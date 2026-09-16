-- Issue #93: collapsible detail-page sections, with an admin-configured
-- expand/collapse default per section. Same singleton shape as
-- floorplan_baseline (0028) -- fixed columns, keyed by id = 1. Confirmed
-- there's no generic key-value settings table anywhere in this repo's
-- migrations, so fixed columns is the right shape for a small, fixed
-- section set; adding a 12th section later is a plain ALTER TABLE ADD
-- COLUMN, no rebuild-and-swap needed.
--
-- Seed defaults below are a starting guess, trivially changeable post-deploy
-- from the new "Detail Page Sections" admin panel with no further code
-- change.
CREATE TABLE IF NOT EXISTS detail_page_sections_config (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  details_expanded INTEGER NOT NULL DEFAULT 1,
  description_features_expanded INTEGER NOT NULL DEFAULT 1,
  nearest_stations_expanded INTEGER NOT NULL DEFAULT 1,
  floorplans_expanded INTEGER NOT NULL DEFAULT 1,
  epc_expanded INTEGER NOT NULL DEFAULT 0,
  room_sizes_expanded INTEGER NOT NULL DEFAULT 0,
  commute_expanded INTEGER NOT NULL DEFAULT 1,
  frequent_destinations_expanded INTEGER NOT NULL DEFAULT 1,
  mortgage_expanded INTEGER NOT NULL DEFAULT 1,
  crime_expanded INTEGER NOT NULL DEFAULT 0,
  jobs_expanded INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO detail_page_sections_config (id) VALUES (1);
