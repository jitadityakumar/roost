-- Replaces listings.comment (0006) / listings.rejection_reason (0004) --
-- both single nullable TEXT columns, overwritten in place with no history,
-- author, or timestamp -- with a proper comments table: every comment
-- (including rejection reasons) gets initials, a timestamp, and can be
-- individually edited/deleted (issue #79).
--
-- created_at/updated_at are nullable here, unlike every other timestamp
-- column in this schema -- deliberate, not an oversight. Backfilled rows
-- (below) have no real creation time or author; the issue's requirement is
-- "don't imply false precision", which no literal timestamp value can
-- satisfy (a frontend can't tell "genuine migration-time" from "genuine
-- user action" once both are valid TEXT timestamps). NULL is the only value
-- that lets the frontend render "-" because it truly doesn't know.
CREATE TABLE comments (
    id            INTEGER PRIMARY KEY,
    listing_id    INTEGER NOT NULL REFERENCES listings(id),
    comment_type  TEXT NOT NULL CHECK (comment_type IN ('general', 'rejection')),
    text          TEXT NOT NULL,
    initials      TEXT,
    created_at    TEXT,
    updated_at    TEXT
);

CREATE INDEX idx_comments_listing_id ON comments(listing_id);

-- Backfill from the old columns, before listings is rebuilt below (these
-- reads must happen against the pre-rebuild table). initials = NULL
-- unconditionally -- no way to recover authorship for old data.
INSERT INTO comments (listing_id, comment_type, text, initials, created_at, updated_at)
SELECT id, 'general', comment, NULL, NULL, NULL FROM listings WHERE comment IS NOT NULL;

INSERT INTO comments (listing_id, comment_type, text, initials, created_at, updated_at)
SELECT id, 'rejection', rejection_reason, NULL, NULL, NULL FROM listings WHERE rejection_reason IS NOT NULL;

-- Rebuild-and-swap to drop comment/rejection_reason -- this project's
-- convention (0002/0004/0017) even though SQLite 3.45 could ALTER TABLE
-- ... DROP COLUMN these two unconstrained, unindexed columns directly, for
-- consistency with every previous column-drop on a CHECK-constrained table.
--
-- listings is referenced by jobs/mortgage_scenarios/station_walk_distances/
-- destination_journeys/journey_scan_pools/comments -- none self-referencing,
-- but DROP TABLE listings still fails under FK enforcement while any of
-- them point at it. Toggled outside a transaction (this file runs via
-- executescript()); DROP TABLE IF EXISTS listings_new guards a crash-restart
-- between CREATE and the final rename, matching 0004/0017 precedent.
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS listings_new;

CREATE TABLE listings_new (
    id                          INTEGER PRIMARY KEY,
    url                         TEXT NOT NULL UNIQUE,

    user_status                 TEXT NOT NULL DEFAULT 'triage'
                                    CHECK (user_status IN ('triage', 'approved', 'rejected')),
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
