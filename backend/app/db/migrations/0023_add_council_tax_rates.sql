-- Issue #60: one row per council, keyed by GSS code (stable even if a
-- council is ever renamed) -- council_name is display-only, never joined
-- on. No FK, no CHECK constraint: validation happens in the route, not the
-- schema, so a future rate-table tweak never needs the rebuild-and-swap /
-- PRAGMA foreign_keys dance other Roost migrations have hit.
DROP TABLE IF EXISTS council_tax_rates;

CREATE TABLE council_tax_rates (
    gss_code      TEXT PRIMARY KEY,
    council_name  TEXT NOT NULL,
    band_a        REAL,
    band_b        REAL,
    band_c        REAL,
    band_d        REAL,
    band_e        REAL,
    band_f        REAL,
    band_g        REAL,
    band_h        REAL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
