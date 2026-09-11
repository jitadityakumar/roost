-- Singleton table holding the traced geometry (rooms + shapes + scale) for
-- the user's own current-residence floor plan, which every listing's trace
-- is compared against. Issue #89.
--
-- The baseline image is stored inline as a data: URI rather than served
-- from a file path -- Roost has no upload endpoint, no /data/baseline
-- directory precedent, and backup.py only snapshots the DB + MEDIA_DIR, so
-- this rides along in the DB backup for free (matches the standalone
-- floorplan-tool's own project.json shape).
--
-- rooms_json/shapes_json as TEXT-encoded JSON is a new storage convention
-- for this codebase (no existing table uses a nested JSON blob) -- kept
-- deliberately, since nothing in the comparison logic needs to query a
-- single shape outside of loading the whole trace at once.
CREATE TABLE IF NOT EXISTS floorplan_baseline (
  id INTEGER PRIMARY KEY CHECK (id = 1),   -- singleton, enforced by fixed PK
  image_blob TEXT,                         -- data: URI of the baseline floor plan
  image_w INTEGER,
  image_h INTEGER,
  active_scale REAL,                       -- px-per-ft, NULL until calibrated
  rooms_json TEXT NOT NULL DEFAULT '[]',   -- JSON array, project.json rooms shape
  shapes_json TEXT NOT NULL DEFAULT '[]',  -- JSON array, project.json shapes shape
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO floorplan_baseline (id) VALUES (1);
