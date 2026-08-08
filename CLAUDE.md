# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Roost tracks house listings you're considering buying. You submit a Rightmove
URL; the backend extracts structured data (price, beds/baths, tenure,
stations, broadband) and tracks it over time as an ongoing shortlist, not a
one-off bookmark. Phase 1 (current state): local-only, no auth, no LLM
enrichment worker, no commute/mortgage joins — those are UI stubs, deferred to
later phases.

## Commands

Backend (from `backend/`):
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # dev server, http://localhost:8000
python3 -m app.db.migrate              # run pending migrations standalone
python3 -m app.backup                  # snapshot DB + media to ../backups/
```

Frontend (from `frontend/`):
```
npm install
npm run dev      # dev server on :5173, proxies /api to localhost:8000 (see vite.config.js)
npm run build    # outputs frontend/dist, consumed by the Docker build
```

Docker (from repo root):
```
docker build -t roost .
docker run -p 8000:8000 -v $(pwd)/data:/data \
  -v ~/.claude:/root/.claude:ro roost
```

There is no automated test suite yet — verification so far has been manual
end-to-end runs against real Rightmove listings and a running Docker
container.

## Architecture

**Migrations are hand-rolled, not a framework.** `backend/app/db/migrate.py`
applies `backend/app/db/migrations/NNNN_*.sql` files in order, tracked in a
`schema_version` table. Add new schema changes as a new numbered file — never
edit an already-applied migration.

**Job queue has two lanes.** The `jobs` table (`app/jobs/queue.py`) has a
`lane` column: `http` (extraction, media downloads — concurrent, currently
2-3 workers via `HttpLaneWorkerPool` in `app/jobs/worker.py`) and `llm`
(vision/text-extraction jobs — `text_extract`, `floor_area_vision`,
`epc_vision` — strictly serial, one worker via `LlmLaneWorkerPool`, Phase 3).
Job claiming uses `BEGIN IMMEDIATE` for atomicity across the two writers
(FastAPI process + worker pool); a `lease_expires_at` lets a dead worker's
`running` job get reclaimed back to `queued` instead of stalling forever
(`reclaim_stale_leases`, polled by the `http`-lane pool only — it has no
lane filter in its query, so it already covers stale `llm`-lane leases too;
don't add a second reclaim loop to `LlmLaneWorkerPool`).

**The `llm`-lane worker shells out to the `claude` CLI**
(`app/jobs/llm_client.py`), not a hosted API — `claude -p --model <model>`,
non-interactive, with `--allowedTools Read` granted only to the two vision
handlers (they need to read an image path; `text_extract`'s prompt embeds a
Rightmove listing description, which is untrusted text with no reason to
carry filesystem access). The container needs the `claude` CLI installed
(see `Dockerfile`) and an authenticated session — mounted read-only from the
host's `~/.claude` at `-v ~/.claude:/root/.claude:ro` (see `README.md`)
rather than a separate `ANTHROPIC_API_KEY`. That mount is read-only, so a
token refresh the CLI would normally persist back to `~/.claude` can't be
written inside the container — if `llm`-lane jobs start failing with an auth
error after the container's been running a while, this is the first thing to
check.

**Every Refresh re-runs all three `llm`-lane jobs, deliberately.**
`llm_enqueue.should_enqueue`'s `has_pending_job` guard only blocks a
duplicate while one is queued/running — it does not skip re-enqueueing a job
type that already completed once. A Refresh re-scrapes and may turn up new
description text or replaced images, so re-running `text_extract` and the
vision jobs (even though the floorplan/EPC images usually haven't changed)
is the current intended behavior, not an oversight — revisit only if the
repeated LLM calls on Refresh turn out to matter at this app's actual usage
volume.

**Rightmove extraction wraps a standalone script, deliberately.**
`app/jobs/rightmove_extract.py` is the original scraping logic
(page-model parsing, media download, broadband lookup) — treat it as a
vendored script, not application code to refactor freely. `app/jobs/handlers.py`
calls into it and does all the DB-writing, normalization, and job-chaining
(a `rightmove_extract` job always enqueues a dependent `media_download` job).

**Every enrichable field can come from more than one source, and users can
override any of them.** `app/listings/store.py` has two write paths:
`apply_extracted_fields` (from a scrape/job — skips any field the user has
manually edited, and *also* skips that field's companion `_source` column via
`FIELD_SOURCE_COMPANIONS` — a manual edit freezes the value and the metadata
describing where it came from together) and `apply_manual_edit` (from a user
PATCH — writes the value and marks it sticky in the `edited_fields` JSON
column). A field's `_source` column (`rightmove` or `llm`) records where the
value *originally* came from; `edited_fields` is what actually blocks future
overwrites, not `_source`. When adding a new enrichable field with a
`_source` companion, add the pair to `FIELD_SOURCE_COMPANIONS` too — a value
field skipped for stickiness whose source column isn't also skipped will
silently mislabel a hand-entered value as machine-sourced.

**When Phase 3 builds the LLM job-enqueue logic: check stickiness before
enqueueing, not just before writing results.** `apply_extracted_fields`
already refuses to overwrite a sticky field's *value*, but that's a
correctness backstop, not an efficiency one — nothing stops a job from being
enqueued and actually running an LLM call whose entire output is guaranteed
to be discarded. Given `lane=llm` is strictly serial (one worker, see below),
that's a wasted turn in a scarce single-threaded queue, not just wasted
compute. Before enqueueing `floor_area_vision`, `epc_vision`, or
`text_extract` for a listing, check whether every field that job would
populate is already in `edited_fields`; if so, skip enqueueing it entirely.
(`text_extract` populates several fields at once — lease years, service
charge, council tax band, chain-free, cash-only — so this is a
job-level "*are all of my target fields already sticky?*" check, not a
per-field one.)

**Media is never served from a bare static mount.** `app/routes/media.py`
validates the listing exists, the category is an allowlisted value, and the
filename has no path-traversal characters, then resolves and re-checks the
real path is still inside the expected directory before serving. Any change
to media serving needs to preserve all three checks.

**URL submission is host-restricted before any network call.**
`app/listings/url_utils.py` extracts the Rightmove property id from the URL
path alone (no fetch) and rejects any host outside `rightmove.co.uk` — this
is the SSRF guard for a URL an end user supplies. Don't relax the host
allowlist without deliberately reconsidering that.

## Working in this repo

This is a **public** repository. Never commit real listing data, credentials,
or personal information — `media/`, `*.db`, and `.env` are gitignored for
this reason. **Never push to `origin` without asking the user first, every
time** — a prior approval to push does not carry over to a later commit.
