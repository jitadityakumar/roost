-- Rename the 2-state user_status (active/in_review) to a 3-state model:
-- 'triage' (renamed from in_review -- where new listings land and sit until
-- reviewed), 'approved' (renamed from active), and a new 'rejected' state.
-- Rejecting requires a reason (enforced at the API layer, not here); the
-- reason is kept as history across a later re-approval rather than cleared,
-- so a new `rejection_reason` column is added (nullable, no CHECK -- only
-- ever required non-null by the API when the transition *into* 'rejected'
-- happens, not enforced at the schema level since it must survive a later
-- move back to 'approved').
--
-- SQLite can't ALTER a CHECK constraint in place, so the table is rebuilt
-- (same dance as 0002 -- see that file's header comment for why
-- PRAGMA foreign_keys is toggled outside a transaction and the DROP IF
-- EXISTS guard is needed for crash-safety).

PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS listings_new;

CREATE TABLE listings_new (
    id                          INTEGER PRIMARY KEY,
    url                         TEXT NOT NULL UNIQUE,

    user_status                 TEXT NOT NULL DEFAULT 'triage'
                                    CHECK (user_status IN ('triage', 'approved', 'rejected')),
    rejection_reason            TEXT,
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
    updated_at                   TEXT NOT NULL
);

INSERT INTO listings_new
SELECT
    id, url,
    CASE user_status WHEN 'active' THEN 'approved' WHEN 'in_review' THEN 'triage' ELSE user_status END,
    NULL,
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
    created_at, updated_at
FROM listings;

DROP TABLE listings;
ALTER TABLE listings_new RENAME TO listings;

PRAGMA foreign_keys=ON;
