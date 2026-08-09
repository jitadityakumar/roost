-- Crime-data comparison (data.police.uk + postcodes.io, ported from the
-- standalone crime-rate-tracker script). Admin-configured baseline
-- postcodes (e.g. current home), and a cache of fetched per-postcode crime
-- stats so a listing-detail page load doesn't re-run a 12-months-of-API-
-- calls fetch every time (see app/crime/service.py -- refreshed only when
-- the cached row is stale).

CREATE TABLE crime_baselines (
    id         INTEGER PRIMARY KEY,
    label      TEXT NOT NULL,
    postcode   TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE crime_stats_cache (
    postcode        TEXT PRIMARY KEY,  -- normalized: upper-cased, whitespace collapsed
    lat             REAL NOT NULL,
    lng             REAL NOT NULL,
    category_counts TEXT NOT NULL,     -- JSON object {category: count}
    fetched_at      TEXT NOT NULL
);
