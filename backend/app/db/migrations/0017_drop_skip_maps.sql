-- Drops jobs.skip_maps (added by migration 0012). It existed solely to let
-- a bulk backfill opt out of Google's *billed* Routes API walking-distance
-- calls (app/commute/walking.py, deleted); TfL's replacement API is free
-- (issue #40), so the opt-out no longer serves a purpose and is removed
-- entirely rather than left dead.
--
-- SQLite has no ALTER TABLE ... DROP CONSTRAINT and this project's
-- convention (0002/0004/0016) is rebuild-and-swap even where a plain
-- ALTER TABLE ... DROP COLUMN would work, for consistency and because
-- executescript() isn't atomic -- a crash partway through leaves
-- jobs_new on disk with schema_version not yet bumped, and the next boot
-- retries this file from the top. The DROP IF EXISTS below makes that
-- retry safe.
--
-- foreign_keys must be off for this rebuild specifically: unlike 0016 (whose
-- rebuilt table only references *other*, untouched tables), jobs.depends_on_job_id
-- is self-referencing (REFERENCES jobs(id)) -- DROP TABLE jobs fails with
-- "FOREIGN KEY constraint failed" while another table (jobs_new) still
-- references it and enforcement is on, same root cause as 0002/0004's
-- listings rebuild. Restored at the end; PRAGMA foreign_keys can't be
-- toggled inside a transaction, and this script runs outside one (executescript).

PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS jobs_new;

CREATE TABLE jobs_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id          INTEGER NOT NULL REFERENCES listings(id),
    job_type            TEXT NOT NULL
                            CHECK (job_type IN (
                                'rightmove_extract', 'media_download',
                                'floor_area_vision', 'epc_vision', 'text_extract'
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
