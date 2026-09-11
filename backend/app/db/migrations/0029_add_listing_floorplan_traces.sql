-- Per-listing floor plan traces, keyed on (listing_id, image_path) since a
-- listing can have multiple floor plan images, each independently traced.
-- Issue #89.
--
-- image_w/image_h are a staleness guard: media filenames under
-- MEDIA_DIR/<listing_id>/floorplans/ are purely positional (01.jpeg,
-- 02.jpeg, ...) and get regenerated on every re-scrape, so the same path
-- can silently point at a different image later. Comparing the served
-- image's dimensions against these on load catches that -- a mismatch
-- means "this floor plan image has changed since it was traced".
CREATE TABLE IF NOT EXISTS listing_floorplan_traces (
  listing_id INTEGER NOT NULL,
  image_path TEXT NOT NULL,
  image_w INTEGER,
  image_h INTEGER,
  active_scale REAL,
  rooms_json TEXT NOT NULL DEFAULT '[]',
  shapes_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (listing_id, image_path),
  FOREIGN KEY (listing_id) REFERENCES listings(id)
);
