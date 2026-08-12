# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Roost tracks house listings you're considering buying. You submit a Rightmove
URL; the backend extracts structured data (price, beds/baths, tenure,
stations, broadband) and tracks it over time as an ongoing shortlist, not a
one-off bookmark. Phase 1 (current state): local-only, no auth, no LLM
enrichment worker (Phase 3, done), and a commute-time join against a
sibling `london-commuter-stations` service (Phase 2, done). Mortgage-
affordability join is still a UI stub, deferred.

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
  -v ~/.claude:/root/.claude:ro \
  --env-file .env \
  --log-opt max-size=10m --log-opt max-file=3 roost
```
`.env` (gitignored, not tracked in this repo) holds the host-specific
`ROOST_COMMUTE_API_BASE`, `ROOST_MORTGAGE_API_BASE`, and
`GOOGLE_MAPS_API_KEY` vars -- deliberately passed via `--env-file` rather
than inline `-e`/python-dotenv, since inline flags leave the key visible in
shell history / `ps aux`.

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
(`app/jobs/llm_client.py`), not a hosted API — `claude -p --model <model>
--output-format json --json-schema <schema>`, non-interactive, with
`--allowedTools Read` granted only to the two vision handlers (they need to
read an image path). `text_extract`'s prompt embeds a Rightmove listing
description — untrusted text with no reason to carry filesystem access — so
it also gets tool access denied; omitting `--allowedTools Read` alone does
NOT block file reads (the CLI has a hardcoded, always-on set of read-only
Bash commands like `cat`/`head` that bypass tool permissions entirely —
confirmed empirically and via https://code.claude.com/docs/en/permissions).
The deny is `--allowedTools StructuredOutput`, not `--disallowedTools "*"` —
confirmed empirically that `--disallowedTools "*"` also denies the CLI's own
internal `StructuredOutput` tool (how `--json-schema` output is actually
delivered), breaking schema output entirely. `--allowedTools <name>` is an
allowlist, so naming only `StructuredOutput` still implicitly denies
everything else. `--json-schema` makes the CLI
validate the model's JSON output against a schema at the source
(`llm_prompts.py`'s `*_SCHEMA` constants); the response envelope's
`structured_output` field (preferred) or its `result` field (fallback, still
code-fenced) is unpacked by `llm_client.parse_structured_output`. The
container needs the `claude` CLI installed
(see `Dockerfile`) and an authenticated session — mounted read-only from the
host's `~/.claude` at `-v ~/.claude:/root/.claude:ro` (see `README.md`)
rather than a separate `ANTHROPIC_API_KEY`. That mount is read-only, so a
token refresh the CLI would normally persist back to `~/.claude` can't be
written inside the container — if `llm`-lane jobs start failing with an auth
error after the container's been running a while, this is the first thing to
check.

**Every Refresh re-runs all three `llm`-lane jobs, by default.**
`llm_enqueue.should_enqueue`'s `has_pending_job` guard only blocks a
duplicate while one is queued/running — it does not skip re-enqueueing a job
type that already completed once. A Refresh re-scrapes and may turn up new
description text or replaced images, so re-running `text_extract` and the
vision jobs (even though the floorplan/EPC images usually haven't changed)
is the current intended default behavior, not an oversight.
`POST /api/listings/{id}/refresh?skip_llm=true` opts a single refresh out of
the whole llm-lane auto-chain (persisted per-job as `jobs.skip_llm_chain`,
checked in both `handle_rightmove_extract` and `handle_media_download` since
the vision jobs chain off `media_download`, not directly off
`rightmove_extract`) — added for `scripts/backfill-rightmove.sh --skip-llm`,
for bulk backfills of a plain scrape-level field (e.g. issue #26's lat/lon)
where re-running the LLM lane on every listing would be pure unwanted spend.

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

**Commute times are fetched live, never persisted.** `app/commute/` resolves
a listing's `nearest_stations_raw` (Rightmove's `[{name, distance, types}]`)
to CRS codes via an in-process, no-network lookup against the bundled
`stations.csv` (`app/commute/stations.py` — National Rail only, tube/tram
entries are filtered out by `types` before lookup, and only stations within
`MAX_DISTANCE_MILES` are kept), then calls `london-commuter-stations`'s API
(`app/commute/client.py`) once per resolved CRS on every
`GET /api/listings/{id}/commute` request. That API's address is **required**
via `ROOST_COMMUTE_API_BASE` (`app/config.py` has no in-repo default — it's
a separate host/service, not something to hardcode into a public repo);
`fetch_station_termini` raises a clear `CommuteApiError` if it's unset
rather than silently no-op'ing. No SSRF allowlist needed here unlike
`url_utils.py` — the host comes from deployer-controlled config, never
user input. A per-station failure is returned inline (`error` set,
`termini: null`) rather than failing the whole request, so one bad station
doesn't take out the others. The `commute_data` table (migration `0005`)
was dropped as part of this — it was never populated and this design has
nothing that would populate it.

**Station walking distance/duration is the opposite: computed once and
persisted, unlike the live commute-termini call above.** `app/commute/
walking.py` calls Google's Routes API v2 (`travelMode: WALK`, reusing
`GOOGLE_MAPS_API_KEY` from `rail-disruption-monitor`) once per station
`resolve_crs_codes()` resolves, from the listing's `latitude`/`longitude`
(migration `0009`) to each station's lat/long in `stations.csv`. This runs
inline in `handle_rightmove_extract` (`app/jobs/handlers.py`) — every
scrape, `/refresh`, and backfill run covers it automatically, no separate
job type or opt-out. Results are stored in `station_walk_distances`
(migration `0011`, `app/commute/walk_store.py`), rows deleted and
reinserted wholesale per listing on each recompute. A per-station Maps
failure (including an unset `GOOGLE_MAPS_API_KEY`) is caught and logged in
`_compute_station_walk_distances`, not raised — the rightmove_extract job
still succeeds, and `GET /api/listings/{id}/commute` falls back to
Rightmove's raw straight-line `distance` for that station.

## Working in this repo

This is a **public** repository. Never commit real listing data, credentials,
or personal information — `media/`, `*.db`, and `.env` are gitignored for
this reason. **Never push to `origin` without asking the user first, every
time** — a prior approval to push does not carry over to a later commit.
