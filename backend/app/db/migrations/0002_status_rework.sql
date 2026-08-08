-- Collapse the 3-state user_status (active/suspended/removed) down to 2
-- (active/in_review). 'removed' was redundant with hard delete (DELETE
-- /api/listings/{id} already exists and cleans up media) so it's dropped
-- entirely rather than kept as a third state. 'suspended' is folded into
-- 'in_review' -- the new state a listing sits in until the user reviews and
-- promotes it. New listings now default to 'in_review' instead of 'active',
-- since they haven't been reviewed yet.
--
-- SQLite can't ALTER a CHECK constraint in place, so the table is rebuilt.
-- foreign_keys must be off for the rebuild: jobs/listing_snapshots/
-- commute_data/mortgage_scenarios all hold a REFERENCES listings(id), and
-- SQLite refuses to DROP a table other tables still reference while
-- enforcement is on. It's restored at the end of this script; PRAGMA
-- foreign_keys can't be toggled inside a transaction, and this script runs
-- outside one (see migrate.py's use of executescript).

PRAGMA foreign_keys=OFF;

DELETE FROM commute_data
    WHERE listing_id IN (SELECT id FROM listings WHERE user_status = 'removed');
DELETE FROM mortgage_scenarios
    WHERE listing_id IN (SELECT id FROM listings WHERE user_status = 'removed');
DELETE FROM listing_snapshots
    WHERE listing_id IN (SELECT id FROM listings WHERE user_status = 'removed');
DELETE FROM jobs
    WHERE listing_id IN (SELECT id FROM listings WHERE user_status = 'removed');

CREATE TABLE listings_new (
    id                          INTEGER PRIMARY KEY,
    url                         TEXT NOT NULL UNIQUE,

    user_status                 TEXT NOT NULL DEFAULT 'in_review'
                                    CHECK (user_status IN ('active', 'in_review')),
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

    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL
);

INSERT INTO listings_new
SELECT
    id, url,
    CASE user_status WHEN 'suspended' THEN 'in_review' ELSE user_status END,
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
    created_at, updated_at
FROM listings
WHERE user_status != 'removed';

DROP TABLE listings;
ALTER TABLE listings_new RENAME TO listings;

PRAGMA foreign_keys=ON;
