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
docker run -p 8000:8000 -v $(pwd)/data:/data roost
```

There is no automated test suite yet — verification so far has been manual
end-to-end runs against real Rightmove listings and a running Docker
container.

## Architecture

**Migrations are hand-rolled, not a framework.** `backend/app/db/migrate.py`
applies `backend/app/db/migrations/NNNN_*.sql` files in order, tracked in a
`schema_version` table. Add new schema changes as a new numbered file — never
edit an already-applied migration.

**Job queue has two lanes, and only one is staffed.** The `jobs` table
(`app/jobs/queue.py`) has a `lane` column: `http` (extraction, media
downloads — concurrent, currently 2-3 workers via `HttpLaneWorkerPool` in
`app/jobs/worker.py`) and `llm` (future vision/text-extraction jobs, strictly
serial). **No worker consumes the `llm` lane yet** — don't enqueue `llm`-lane
jobs from application code until that worker exists, or they'll sit forever.
Job claiming uses `BEGIN IMMEDIATE` for atomicity across the two writers
(FastAPI process + worker pool); a `lease_expires_at` lets a dead worker's
`running` job get reclaimed back to `queued` instead of stalling forever
(`reclaim_stale_leases`, polled by the worker pool).

**Rightmove extraction wraps a standalone script, deliberately.**
`app/jobs/rightmove_extract.py` is the original scraping logic
(page-model parsing, media download, broadband lookup) — treat it as a
vendored script, not application code to refactor freely. `app/jobs/handlers.py`
calls into it and does all the DB-writing, normalization, and job-chaining
(a `rightmove_extract` job always enqueues a dependent `media_download` job).

**Every enrichable field can come from more than one source, and users can
override any of them.** `app/listings/store.py` has two write paths:
`apply_extracted_fields` (from a scrape/job — skips any field the user has
manually edited) and `apply_manual_edit` (from a user PATCH — writes the
value and marks it sticky in the `edited_fields` JSON column). A field's
`_source` column (`rightmove` or `llm`) records where the value *originally*
came from; `edited_fields` is what actually blocks future overwrites, not
`_source`. When adding a new enrichable field, decide its source priority
order and wire both write paths consistently — don't bypass
`apply_extracted_fields` with a raw UPDATE from job code.

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
