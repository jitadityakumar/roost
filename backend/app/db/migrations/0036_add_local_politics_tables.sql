-- Issue #61: shared local-politics reference data, both keyed by GSS code
-- (same precedent as council_tax_rates, 0023) so listings in the same
-- council/constituency share one row. Names are display-only, never joined
-- on. No FK/CHECK constraints -- plain additive, no rebuild-and-swap needed.
--
-- council_composition is imported once from the Open Council Data UK CSV
-- and never re-downloaded; `previous_json` holds the prior year's
-- {"year", "total", "parties"} for the "vs previous year" column.
CREATE TABLE IF NOT EXISTS council_composition (
    gss_code       TEXT PRIMARY KEY,
    council_id     INTEGER NOT NULL,
    authority      TEXT NOT NULL,
    year           INTEGER NOT NULL,
    total          INTEGER NOT NULL,
    con            INTEGER NOT NULL DEFAULT 0,
    lab            INTEGER NOT NULL DEFAULT 0,
    ld             INTEGER NOT NULL DEFAULT 0,
    green          INTEGER NOT NULL DEFAULT 0,
    ukip           INTEGER NOT NULL DEFAULT 0,
    ref            INTEGER NOT NULL DEFAULT 0,
    pc             INTEGER NOT NULL DEFAULT 0,
    snp            INTEGER NOT NULL DEFAULT 0,
    other          INTEGER NOT NULL DEFAULT 0,
    previous_json  TEXT
);

-- Sitting MP per constituency, resolved via the UK Parliament Members API
-- by exact constituency name (it can't be queried by GSS).
CREATE TABLE IF NOT EXISTS constituency_mp (
    constituency_gss    TEXT PRIMARY KEY,
    constituency_name   TEXT NOT NULL,
    members_api_id      INTEGER NOT NULL,
    member_id           INTEGER NOT NULL,
    member_name         TEXT NOT NULL,
    party_name          TEXT,
    party_abbreviation  TEXT,
    party_colour        TEXT,
    result              TEXT,
    majority            INTEGER,
    turnout             INTEGER,
    electorate          INTEGER,
    updated_at          TEXT NOT NULL
);
