-- Extends the listing status model from 3 states to 5 (issue #82): adds
-- 'viewing' and 'contacted' to listings.user_status, and matching
-- comment_type values to comments (each of rejected/viewing/contacted gets
-- its own comment_type, per the mandatory-comment-on-entry design decision).
--
-- Rebuild-and-swap both tables (SQLite can't ALTER a CHECK constraint).
-- comments has no self-referencing FK and nothing references *it*, so its
-- rebuild doesn't need the foreign_keys pragma dance -- only listings does
-- (jobs/mortgage_scenarios/station_walk_distances/destination_journeys/
-- journey_scan_pools/comments all reference it), same as migration 0025.

DROP TABLE IF EXISTS comments_new;

CREATE TABLE comments_new (
    id            INTEGER PRIMARY KEY,
    listing_id    INTEGER NOT NULL REFERENCES listings(id),
    comment_type  TEXT NOT NULL CHECK (comment_type IN ('general', 'rejection', 'viewing', 'contacted')),
    text          TEXT NOT NULL,
    initials      TEXT,
    created_at    TEXT,
    updated_at    TEXT
);

INSERT INTO comments_new SELECT id, listing_id, comment_type, text, initials, created_at, updated_at FROM comments;

DROP TABLE comments;
ALTER TABLE comments_new RENAME TO comments;

CREATE INDEX idx_comments_listing_id ON comments(listing_id);

PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS listings_new;

CREATE TABLE listings_new (
    id                          INTEGER PRIMARY KEY,
    url                         TEXT NOT NULL UNIQUE,

    user_status                 TEXT NOT NULL DEFAULT 'triage'
                                    CHECK (user_status IN ('triage', 'approved', 'rejected', 'viewing', 'contacted')),
    rightmove_status            TEXT,

    extraction_status           TEXT NOT NULL DEFAULT 'queued'
                                    CHECK (extraction_status IN ('queued', 'running', 'done', 'failed')),
    extraction_error            TEXT,

    price_gbp                   INTEGER,
    address                     TEXT,
    postcode                    TEXT,
    property_type               TEXT,
    bedrooms                    INTEGER,
    bathrooms                   INTEGER,
    tenure                      TEXT,
    description                 TEXT,
    key_features                TEXT,
    nearest_stations_raw        TEXT,
    agent_branch                TEXT,
    agent_address                TEXT,

    lease_years_remaining       INTEGER,
    lease_years_remaining_source TEXT CHECK (lease_years_remaining_source IN ('rightmove', 'llm')),

    service_charge_pa           INTEGER,
    service_charge_pm           INTEGER,
    service_charge_source       TEXT CHECK (service_charge_source IN ('rightmove', 'llm')),

    council_tax_band            TEXT,
    council_tax_band_source     TEXT CHECK (council_tax_band_source IN ('rightmove', 'llm')),

    floor_area_sqft             REAL,
    floor_area_sqft_source      TEXT CHECK (floor_area_sqft_source IN ('rightmove', 'llm')),

    epc_current                 TEXT,
    epc_potential                TEXT,
    epc_source                  TEXT CHECK (epc_source IN ('rightmove', 'llm')),

    chain_free                  INTEGER CHECK (chain_free IN (0, 1)),
    chain_free_source           TEXT CHECK (chain_free_source IN ('rightmove', 'llm')),

    cash_only                   INTEGER CHECK (cash_only IN (0, 1)),
    cash_only_source            TEXT CHECK (cash_only_source IN ('rightmove', 'llm')),

    garden                      INTEGER CHECK (garden IN (0, 1)),
    garden_source                TEXT CHECK (garden_source IN ('rightmove', 'llm')),

    parking                     TEXT,
    parking_source               TEXT CHECK (parking_source IN ('rightmove', 'llm')),

    broadband_top_speed          TEXT,
    broadband_top_speed_category TEXT,
    broadband_top_speed_provider TEXT,

    edited_fields                TEXT NOT NULL DEFAULT '{}',

    listing_added_on             TEXT,
    rightmove_fetched_at         TEXT,

    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL,

    latitude                     REAL,
    longitude                    REAL,
    pin_type                     TEXT,
    admin_district                TEXT,
    admin_district_gss            TEXT
);

INSERT INTO listings_new
SELECT
    id, url,
    user_status,
    rightmove_status,
    extraction_status, extraction_error,
    price_gbp, address, postcode, property_type, bedrooms, bathrooms, tenure,
    description, key_features, nearest_stations_raw, agent_branch, agent_address,
    lease_years_remaining, lease_years_remaining_source,
    service_charge_pa, service_charge_pm, service_charge_source,
    council_tax_band, council_tax_band_source,
    floor_area_sqft, floor_area_sqft_source,
    epc_current, epc_potential, epc_source,
    chain_free, chain_free_source,
    cash_only, cash_only_source,
    garden, garden_source,
    parking, parking_source,
    broadband_top_speed, broadband_top_speed_category, broadband_top_speed_provider,
    edited_fields,
    listing_added_on, rightmove_fetched_at,
    created_at, updated_at,
    latitude, longitude, pin_type,
    admin_district, admin_district_gss
FROM listings;

DROP TABLE listings;
ALTER TABLE listings_new RENAME TO listings;

PRAGMA foreign_keys=ON;
