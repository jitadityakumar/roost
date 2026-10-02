-- Issue #115: manually attach a gov.uk EPC certificate URL to a listing.
--
-- listings.epc_certificate_url   canonical certificate URL (user-supplied,
--                                validated by app/epc_certificate/url.py)
-- listings.epc_certificate_data  JSON blob of the parsed certificate (address,
--                                ratings, features table, recommended steps,
--                                and extra figures stored for later use) --
--                                same JSON-blob convention as 0028-0030's
--                                floorplan traces. NULL until the fetch job
--                                has succeeded.
-- Being plain listings columns (not a child table), neither needs adding to
-- store.delete_listing.
--
-- jobs.job_type has a CHECK constraint, so the new 'epc_certificate_fetch'
-- type needs a rebuild-and-swap of jobs, same as 0017 (see its header for
-- why foreign_keys must be off: jobs.depends_on_job_id is self-referencing).
-- Restored at the end; PRAGMA foreign_keys can't be toggled inside a
-- transaction and this script runs outside one (executescript).

PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS jobs_new;

CREATE TABLE jobs_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          INTEGER NOT NULL REFERENCES listings(id),
    job_type            TEXT NOT NULL
                            CHECK (job_type IN (
                                'rightmove_extract', 'media_download',
                                'floor_area_vision', 'epc_vision', 'text_extract',
                                'epc_certificate_fetch'
                            )),
    lane                TEXT NOT NULL CHECK (lane IN ('http', 'llm')),
    status              TEXT NOT NULL DEFAULT 'queued'
                            CHECK (status IN ('queued', 'running', 'done', 'failed')),
    depends_on_job_id   INTEGER REFERENCES jobs(id),
    attempts            INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    heartbeat_at        TEXT,
    lease_expires_at    TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    skip_llm_chain      INTEGER NOT NULL DEFAULT 0
);

INSERT INTO jobs_new (
    id, listing_id, job_type, lane, status, depends_on_job_id, attempts,
    last_error, heartbeat_at, lease_expires_at, created_at, updated_at, skip_llm_chain
)
SELECT
    id, listing_id, job_type, lane, status, depends_on_job_id, attempts,
    last_error, heartbeat_at, lease_expires_at, created_at, updated_at, skip_llm_chain
FROM jobs;

DROP TABLE jobs;

ALTER TABLE jobs_new RENAME TO jobs;

CREATE INDEX idx_jobs_listing_id ON jobs(listing_id);
CREATE INDEX idx_jobs_status_lane ON jobs(status, lane);

PRAGMA foreign_keys=ON;

-- The ALTERs go last on purpose: executescript() isn't atomic and a rerun
-- after a crash dies on "duplicate column name" for an ALTER that already
-- ran, whereas everything above is safe to repeat (DROP IF EXISTS jobs_new,
-- and rebuilding an already-rebuilt jobs is harmless). That leaves the
-- crash window at the very end of the file.
ALTER TABLE listings ADD COLUMN epc_certificate_url TEXT;
ALTER TABLE listings ADD COLUMN epc_certificate_data TEXT;
