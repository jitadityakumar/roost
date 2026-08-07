-- Roost Phase 1 initial schema.
--
-- Field-source model: fields with more than one possible origin carry a
-- companion `<field>_source` column (values: 'rightmove' or 'llm', recording
-- where the value *originally* came from). Manual edits are tracked
-- separately in `listings.edited_fields` (a JSON object of
-- {field_name: iso_timestamp}) rather than a per-field `_edited_at` column —
-- one sticky-edit mechanism for every editable field, multi-source or not.
-- A field present in `edited_fields` must never be overwritten by a later
-- scrape or job.

CREATE TABLE listings (
    id                          INTEGER PRIMARY KEY,  -- Rightmove property id
    url                         TEXT NOT NULL UNIQUE,

    -- Lifecycle: user's own judgement call vs. Rightmove's own listing state.
    -- These are separate axes and never drive each other automatically.
    user_status                 TEXT NOT NULL DEFAULT 'active'
                                    CHECK (user_status IN ('active', 'removed', 'suspended')),
    rightmove_status            TEXT,  -- e.g. 'Available', 'SSTC', 'Sold' — Rightmove's own text

    extraction_status           TEXT NOT NULL DEFAULT 'queued'
                                    CHECK (extraction_status IN ('queued', 'running', 'done', 'failed')),
    extraction_error            TEXT,

    -- Single-source fields (Rightmove structured data only, no priority ambiguity)
    price_gbp                   INTEGER,
    address                     TEXT,
    postcode                    TEXT,
    property_type               TEXT,
    bedrooms                    INTEGER,
    bathrooms                   INTEGER,
    tenure                      TEXT,
    description                 TEXT,
    key_features                TEXT,  -- JSON array
    nearest_stations_raw        TEXT,  -- JSON array, pre-resolution against london-commuter-stations
    agent_branch                TEXT,
    agent_address               TEXT,

    -- Multi-source enriched fields: Rightmove structured/text tried first,
    -- LLM text/vision extraction as fallback (see field-source-priority notes
    -- in context.md). chain_free/cash_only/EPC have only the LLM source.
    lease_years_remaining       INTEGER,
    lease_years_remaining_source TEXT CHECK (lease_years_remaining_source IN ('rightmove', 'llm')),

    service_charge_pa           INTEGER,
    service_charge_pm           INTEGER,
    service_charge_source       TEXT CHECK (service_charge_source IN ('rightmove', 'llm')),

    council_tax_band            TEXT,
    council_tax_band_source     TEXT CHECK (council_tax_band_source IN ('rightmove', 'llm')),

    floor_area_sqft             REAL,  -- normalized to sqft at write time regardless of source unit
    floor_area_sqft_source      TEXT CHECK (floor_area_sqft_source IN ('rightmove', 'llm')),

    epc_current                 TEXT,  -- e.g. "C (73)"
    epc_potential                TEXT,
    epc_source                  TEXT CHECK (epc_source IN ('rightmove', 'llm')),

    chain_free                  INTEGER CHECK (chain_free IN (0, 1)),  -- nullable tri-state
    chain_free_source           TEXT CHECK (chain_free_source IN ('rightmove', 'llm')),

    cash_only                   INTEGER CHECK (cash_only IN (0, 1)),
    cash_only_source            TEXT CHECK (cash_only_source IN ('rightmove', 'llm')),

    garden                      INTEGER CHECK (garden IN (0, 1)),  -- nullable tri-state
    garden_source                TEXT CHECK (garden_source IN ('rightmove', 'llm')),

    parking                     TEXT,  -- free text (e.g. "Garage", "Off street") or 'yes'/'no'
    parking_source               TEXT CHECK (parking_source IN ('rightmove', 'llm')),

    -- Broadband: single-source (Rightmove's broadband API), no priority ambiguity
    broadband_top_speed          TEXT,
    broadband_top_speed_category TEXT,
    broadband_top_speed_provider TEXT,

    -- Sticky manual edits: {"price_gbp": "2026-08-07T12:00:00Z", ...}
    edited_fields                TEXT NOT NULL DEFAULT '{}',

    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL
);

CREATE TABLE listing_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          INTEGER NOT NULL REFERENCES listings(id),
    captured_at         TEXT NOT NULL,
    price_gbp           INTEGER,
    rightmove_status    TEXT,
    raw_json            TEXT NOT NULL  -- full extracted payload at this point in time
);

CREATE INDEX idx_listing_snapshots_listing_id ON listing_snapshots(listing_id);

CREATE TABLE jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          INTEGER NOT NULL REFERENCES listings(id),
    job_type            TEXT NOT NULL
                            CHECK (job_type IN (
                                'rightmove_extract', 'media_download',
                                'floor_area_vision', 'epc_vision', 'text_extract'
                            )),
    -- 'llm' = strictly serial (one worker, Phase 3). 'http' = commute/mortgage/
    -- extraction/media lookups, safe to run concurrently (Phase 1 worker pool).
    lane                TEXT NOT NULL CHECK (lane IN ('http', 'llm')),
    status              TEXT NOT NULL DEFAULT 'queued'
                            CHECK (status IN ('queued', 'running', 'done', 'failed')),
    depends_on_job_id   INTEGER REFERENCES jobs(id),
    attempts            INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    heartbeat_at        TEXT,
    lease_expires_at    TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX idx_jobs_listing_id ON jobs(listing_id);
CREATE INDEX idx_jobs_status_lane ON jobs(status, lane);

CREATE TABLE commute_data (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          INTEGER NOT NULL REFERENCES listings(id),
    station_name        TEXT NOT NULL,
    crs_code            TEXT,
    distance_miles      REAL NOT NULL,
    is_nearest          INTEGER NOT NULL DEFAULT 0 CHECK (is_nearest IN (0, 1)),
    journey_time_mins   INTEGER,
    trains_per_hour     INTEGER
);

CREATE INDEX idx_commute_data_listing_id ON commute_data(listing_id);

CREATE TABLE mortgage_scenarios (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id              INTEGER NOT NULL REFERENCES listings(id),
    property_value_gbp      INTEGER NOT NULL,
    deposit_gbp              INTEGER,
    fixed_rate_annual_pct   REAL,
    fixed_term_months       INTEGER,
    variable_rate_annual_pct REAL,
    total_term_months       INTEGER,
    result_json             TEXT,
    created_at              TEXT NOT NULL
);

CREATE INDEX idx_mortgage_scenarios_listing_id ON mortgage_scenarios(listing_id);
