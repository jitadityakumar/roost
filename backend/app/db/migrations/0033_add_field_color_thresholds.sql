-- Issue #100: admin-configurable green/amber/red colour thresholds for a
-- handful of Details fields. One row per field ("field" as the natural
-- key), modeled on standards_rules (0007) rather than
-- detail_page_sections_config's fixed-column singleton (0032) -- unlike
-- the fixed sections list, the colourable field set could plausibly grow.
--
-- green_cutoff/red_cutoff are stored as TEXT (a numeric string, or an EPC
-- band letter for epc_current) since the same column has to hold both
-- representations depending on the field -- mirrors standards_rules.value.
-- NULL on either means "no rule on that side" (e.g. only a red cutoff set).
-- higher_is_better is NULL for epc_current, whose band order (A best..G
-- worst) is fixed, not admin-flippable.
--
-- No seed rows -- admin sets these up from a blank state, same as
-- standards_rules starts empty.
CREATE TABLE IF NOT EXISTS field_color_thresholds (
  field TEXT PRIMARY KEY,
  green_cutoff TEXT,
  red_cutoff TEXT,
  higher_is_better INTEGER,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
