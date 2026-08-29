# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Roost tracks house listings you're considering buying. You submit a Rightmove
URL; the backend extracts structured data (price, beds/baths, tenure,
stations, broadband) and tracks it over time as an ongoing shortlist, not a
one-off bookmark. Local-only, no auth, single SQLite file, single Docker
container.

Beyond the core scrape-and-track flow, every other feature is an optional
join against an external dependency, and every one of them fails soft (the
feature reports unavailable / is skipped — nothing else breaks) when its
dependency is missing: LLM-enriched fields (needs the `claude` CLI + an
authenticated session, "Phase 3" in commit history), a commute-time join
against a sibling `london-commuter-stations` service ("Phase 2"), a
mortgage-affordability join against a sibling `mortgage-calculator` service,
TfL-based nearest-station walking distance and frequent-destination journey
times (needs a free `TFL_API_KEY`), a home-vs-listing commute comparison
(needs home lat/lon env vars), and crime-rate/council-tax lookups against
two free public APIs (postcodes.io, data.police.uk). See README.md's
Requirements section for the full table of what each needs and what happens
if it's absent — that table is written for someone (human or agent) setting
this up fresh and deciding what to configure.

## Commands

Backend (from `backend/`):
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # dev server, http://localhost:8000
python3 -m app.db.migrate              # run pending migrations standalone
python3 -m app.backup                  # snapshot DB + media to ../backups/
```

Testing (from repo root):
```
scripts/test.sh   # backend pytest (backend/tests/) + frontend vitest (frontend/src/tests/)
scripts/e2e.sh    # Playwright suite (e2e/) against a throwaway Docker container
```
`scripts/test.sh` installs `backend/requirements-dev.txt` (pytest, httpx —
separate from `requirements.txt`, dev/test only) into `backend/.venv`
automatically. Both backend and frontend suites run entirely against
fixtures/mocks, not the real Rightmove/TfL/commute/mortgage/crime
dependencies. `scripts/e2e.sh` is slower and needs Docker; run it before a
release, not on every change.

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
  --add-host=host.docker.internal:host-gateway \
  --env-file .env \
  --log-opt max-size=10m --log-opt max-file=3 roost
```
`.env` (gitignored, not tracked in this repo) holds the host-specific
`ROOST_COMMUTE_API_BASE`, `ROOST_MORTGAGE_API_BASE`, `TFL_API_KEY`,
`ROOST_LLM_BRIDGE_BASE` (the host-side LLM bridge's address, e.g.
`http://host.docker.internal:8094` -- see "Architecture" below and
`host/llm_bridge/`), and optional `ROOST_HOME_LAT`/`ROOST_HOME_LON`
(home-vs-listing journey duration comparison, app/destinations/compute.py
-- deliberately env-only, never DB-stored, so a real home address never
lands in the public repo or a DB dump; the comparison is just skipped if
unset) vars -- deliberately passed via `--env-file` rather than inline
`-e`/python-dotenv, since inline flags leave the key visible in shell
history / `ps aux`.

Host-side LLM bridge (from `host/llm_bridge/`, a second independent
Python project -- own venv, not part of the container build):
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m llm_bridge      # dev/manual run, http://localhost:8094
```
See `host/llm_bridge/README.md` for the systemd unit install steps.

See "Testing" above for the automated suites (`scripts/test.sh`,
`scripts/e2e.sh`). Beyond those, some verification is still manual
end-to-end runs against real Rightmove listings and a running Docker
container — in particular, anything that depends on live third-party
response shapes (Rightmove's page structure, TfL/commute/mortgage API
responses) rather than logic the fixtures already cover.

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

**The `llm`-lane worker calls a host-side HTTP bridge, not a local CLI or a
hosted API** (issue #73). `app/jobs/llm_client.py`'s `run_claude_prompt`
POSTs to `{ROOST_LLM_BRIDGE_BASE}/v1/llm/<job_type>`; the bridge
(`host/llm_bridge/`, a second, host-resident deployable living alongside the
container, own venv/entrypoint, autostarted via a systemd unit) is what
actually runs `claude -p --model <model> --output-format json --json-schema
<schema>`, non-interactive, with `--allowedTools Read` granted only for the
two vision handlers (they need to read an image path) — `text_extract`'s
prompt embeds a Rightmove listing description — untrusted text with no
reason to carry filesystem access — so it gets tool access denied instead;
omitting `--allowedTools Read` alone does NOT block file reads (the CLI has
a hardcoded, always-on set of read-only Bash commands like `cat`/`head` that
bypass tool permissions entirely — confirmed empirically and via
https://code.claude.com/docs/en/permissions). The deny is `--allowedTools
StructuredOutput`, not `--disallowedTools "*"` — confirmed empirically that
`--disallowedTools "*"` also denies the CLI's own internal
`StructuredOutput` tool (how `--json-schema` output is actually delivered),
breaking schema output entirely. `--allowedTools <name>` is an allowlist, so
naming only `StructuredOutput` still implicitly denies everything else.
`--json-schema` makes the CLI validate the model's JSON output against a
schema at the source (`llm_prompts.py`'s `*_SCHEMA` constants); the response
envelope's `structured_output` field (preferred) or its `result` field
(fallback, still code-fenced) is unpacked by
`llm_client.parse_structured_output`, unchanged from before this moved
host-side — only the transport (HTTP to the bridge, not a local subprocess)
changed.

Vision jobs send the image as base64 bytes in the request body (not a file
path — the container and the bridge aren't assumed to share a filesystem).
The prompt sent to the bridge embeds a fixed sentinel,
`llm_prompts.ATTACHED_IMAGE_SENTINEL` (`"<<ATTACHED_IMAGE>>"`), where the
image path used to go; the bridge string-replaces it with its own temp
file's path before invoking `claude -p`. The bridge has zero knowledge of
`llm_prompts.py`'s other template variables or Roost's prompt content by
design — this sentinel is duplicated (not imported) in
`host/llm_bridge/config.py`, with a test on each side asserting the literal
value so a one-sided edit fails its own suite.

The bridge runs as the host user (not root) with normal read-write access
to `~/.claude`, so token refresh Just Works there — this is what actually
fixes issue #73's failure mode (the container's old `~/.claude:ro` mount
meant a refreshed token could never be persisted back to the host). The
container no longer touches `~/.claude` at all. See `host/llm_bridge/`'s own
files for the bridge's HTTP surface, backend-interface pattern, and
systemd unit; `host/llm_bridge/README.md` for manual install steps (a
host-level operation, not part of this repo's `docker build`/`docker run`
flow).

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
tfl_client.py` calls TfL's free Unified API (`api.tfl.gov.uk`) once per
station: `resolve_stop_point` maps a Rightmove station name to a TfL
StopPoint id (free-text search, disambiguated against Rightmove's own
stated straight-line distance -- plain closest-lat/lon mis-resolved real
stations in testing, see issue #40's plan comment for the validated fix),
then `compute_walk_distance` calls TfL's Journey Planner from the listing's
`latitude`/`longitude` (migration `0009`) to that StopPoint id. Replaced the
billed Google Routes API (`walking.py`, deleted) in issue #40 -- TfL is
free, so there's no opt-out flag (the old `skip_maps`/`--skip-maps` was
removed entirely, migration `0017`). This runs inline in
`handle_rightmove_extract` (`app/jobs/handlers.py`) — every scrape,
`/refresh`, and backfill run covers it automatically, no separate job type.
Also callable directly without a Rightmove re-scrape, via
`POST /api/listings/{id}/walk-refresh` (`compute_station_walk_distances`
is public specifically so this route can call it against already-stored
`latitude`/`longitude`/`nearest_stations_raw` -- synchronous, not queued,
since it's just a couple of TfL calls, no HTML fetch/parse) --
`scripts/tfl-walk-backfill.sh` backfills every listing this way, for when a
walk-distance-computation change needs re-running but the underlying
Rightmove data hasn't changed.

**Every mode, no radius cap (issue #40 PR2)** — `compute_station_walk_
distances` iterates `nearest_stations_raw` directly (not `resolve_crs_
codes()`, which stays national-rail/1mi-only and is now solely the Commute
section's own candidate set below), mapping each entry's Rightmove `types`
to a TfL mode via `_TFL_MODE_BY_TYPE` (`handlers.py`) -- an unmapped type is
skipped with a log line, not fatal. Results are stored in
`station_walk_distances` (migration `0011`, re-keyed by migration `0018`,
`app/commute/walk_store.py`), rows deleted and reinserted wholesale per
listing on each recompute. **Keyed by `(listing_id, station_index)`, not
CRS** -- tube/tram/DLR/overground stations have no CRS code, and
`nearest_stations_raw` is always fully replaced (not merged) on every
scrape, so positional keying is stable within one scrape and needs no
name-matching to re-attach a row at render time. Every row also stores
`rightmove_name`, and every reader (`routes/listings.py`'s `_attach_walk_
data`, `routes/commute.py`) must look it up via `walk_store.lookup_walk()`,
which checks the stored `rightmove_name` still matches the name currently
at that index before returning a row -- guards against Rightmove reordering
its nearest-3 between scrapes silently attaching the wrong station's
distance (index-keying alone degrades *unsafely* without this; CRS-keying
degraded safely, no match = no data). A per-station TfL failure (including
an unset `TFL_API_KEY`, an unmapped mode, or a name TfL can't resolve) is
caught and logged in `compute_station_walk_distances`, not raised — the
rightmove_extract job still succeeds, and `GET /api/listings/{id}/commute`
falls back to Rightmove's raw straight-line `distance` for that station.
**The Commute section's scope is unchanged** — it's still national-rail-only
via `resolve_crs_codes()`'s 1mi radius (`fetch_station_termini` is a
separate, national-rail-only integration keyed by CRS); tube/tram/DLR/
overground stations get a walking distance/time in Nearest Stations only,
same section boundary as before this PR.

**Frequent-destination journeys, computed once and persisted (issue #28,
fully moved onto TfL by issue #47) -- same "compute at scrape time, never
live" precedent as station walking distance above.** `app/destinations/`
lets the admin define named destinations (`frequent_destinations`,
migration `0013`, reshaped by migration `0019`) with a target day-of-week +
time and either a TfL StopPoint id (`destination_type = "station"`,
resolved via `GET /api/destinations/stations/search` ->
`tfl_client.search_stop_points()`, a live `/StopPoint/Search` proxy
excluding `bus`/`river-bus`/`coach`) or a raw UK postcode
(`destination_type = "postcode"` -- TfL's `to` param accepts a postcode
directly, no resolution step). For each enabled destination,
`app/destinations/compute.py` calls
`tfl_client.find_frequent_destination_journey()` **once**, using the
listing's own raw `latitude`/`longitude` as `from` -- no per-station
candidate loop, no CRS requirement, which is what lets this reach
Tube/DLR/Overground/tram-only stations the old CRS-only GTFS planner
structurally couldn't (Southfields, Pudding Mill Lane). That function does
a windowed scan (walks forward across a rolling 60-minute window,
re-querying TfL's `/Journey/JourneyResults` as needed) for the next
upcoming occurrence of the destination's day/time, and returns the fastest
journey found, reading `duration` directly off TfL's response rather than
diffing timestamps (DST-ambiguous around the fall-back hour, confirmed
live). This runs inline in `handle_rightmove_extract`, unconditionally --
TfL's API is free, same as its walking-distance API above, so there's no
opt-out flag -- and again on manual
`POST /api/listings/{id}/destinations/refresh`. Results are stored in
`destination_journeys` (migration `0014`, widened by `0019` with
`arrival_name`; `app/destinations/journey_store.py`), rows deleted and
reinserted wholesale per listing on each recompute. A destination with no
`tfl_identifier` yet, a listing with no resolved lat/lon, or no journey
found in the scan window simply gets no stored row -- `GET
/api/listings/{id}/destinations` reports that as `resolved: false`, which
the frontend renders as "no journey found" rather than an error.

**Walking-leg counting.** A TfL journey from a raw lat/lon always starts
with a walking leg (access), and can also insert a walking leg *between*
two transit legs for a genuine cross-station interchange (e.g. Bank ->
Monument) -- only the very first leg (if walking) and very last leg (if
walking, egress to a postcode/StopPoint) are excluded from
`kind`/`num_changes`/`interchange_crs`; a walking leg anywhere in the
middle counts as a change like any other mode transition
(`tfl_client.py::_counted_legs`). `origin_crs`/`origin_name` hold the first
counted leg's StopPoint id/`commonName` (repurposed, not schema-changed,
from the old CRS-based meaning); `arrival_name` (migration `0019`) holds
the last counted leg's `commonName` -- needed so a postcode-type
destination's resolved arrival station has something to display
(`FrequentDestinations.jsx`'s `{origin_name} -> {arrival_name}` line).

**Home-vs-listing commute comparison, keyed by destination alone.**
`home_journeys` (migration `0020`) stores one row per `frequent_destinations`
row — not per `(listing, destination)` like `destination_journeys` — because
home is a single fixed origin (`ROOST_HOME_LAT`/`ROOST_HOME_LON`) shared
across every listing's comparison, not something listing-specific.
`compute.py`'s `compute_for_destination` recomputes it on every call, same
function used for the per-listing backfill, so a `PATCH` to a destination's
day/time/`tfl_identifier` is picked up correctly — the admin UI just never
exposes editing those fields today (delete + recreate only), so in practice
it only ever runs once per destination's lifetime. Only the fields needed
for a live duration diff are stored (no operator/origin_name/arrival_name/
times) — the home journey itself is never rendered, only diffed against a
listing's own stored `duration_minutes` at read time
(`routes/destination_journeys.py`). Skipped entirely if the home lat/lon
env vars are unset.

**Journey scan pools, for a "why this journey was picked" details page**
(issue #59). `journey_scan_pools` (migration `0021`,
`app/destinations/journey_store.py`) stores the raw candidate journey pool
TfL returned during the windowed scan behind each `destination_journeys`
row — `listing_id` is `NOT NULL`; home journeys are explicitly out of scope
here, there's no home-origin variant of this table the way there is for
`destination_journeys`/`home_journeys`. Overwritten per scan (`UNIQUE
(listing_id, destination_id)`), not an append-only history — same
delete-then-reinsert precedent as `destination_journeys` itself.
`GET /api/journey-details/{pool_id}` (`routes/journey_details.py`) serves it
for the frontend's details page.

**Standards rules are advisory-only and never write back to `listings`.**
`app/standards/` (`standards_rules` table, migration `0007`) lets the admin
define simple threshold rules — a field, an operator
(`lt`/`lte`/`gt`/`gte`/`eq`/`neq`), and a value stored as text and cast per
the field's real type at eval time (`fields.py`) — evaluated against a
listing on the detail page (`evaluate.py`) to flag properties that don't
meet the user's own baseline criteria (e.g. "floor area < 700 sqft"). No
external dependency; purely a DB-configured comparison against fields
already on the listing.

**Crime-rate comparison, backed by two free public APIs.**
`app/crime/` (`crime_baselines` + `crime_stats_cache` tables, migration
`0008`) lets the admin configure baseline postcodes (e.g. current home) via
`POST /api/crime/baselines`, then `GET /api/listings/{id}/crime`
(`routes/crime.py`) compares a listing's postcode against them.
`app/crime/client.py` calls `api.postcodes.io` (geocoding a postcode to
lat/lng, and separately — shared with the council-tax feature below —
resolving a postcode's local authority + GSS code) and
`data.police.uk`'s `crimes-street` endpoints (ported from a standalone
`crime-rate-tracker` script). Neither API takes a key; both are fixed public
hosts, not deployer-configured like the commute/mortgage sibling services,
and a postcode only ever feeds a query param, never a URL, so there's no
SSRF concern here (same reasoning as `url_utils.py`'s allowlist not
applying). `crimes-street` only accepts one month per request (no
date-range param), so a full 12-month fetch is ~13 calls per postcode
(1 geocode + 12 months); `data.police.uk` allows 15 req/s sustained / burst
30 and returns 429 over that, so every call is throttled with a fixed delay
plus exponential backoff on 429 (`_throttled_get`). Results are cached in
`crime_stats_cache` keyed by normalized postcode
(`app/crime/service.py::get_or_refresh_stats`, refreshed only when the
cached row is stale) so a listing-detail page load doesn't re-run the full
fetch every time. `scripts/crime-backfill.sh` warms the cache for an entire
existing shortlist plus baselines in one pass.

**Council tax band estimate, sharing the crime feature's postcode client.**
`app/counciltax/` + `council_tax_rates` table (migrations `0022`/`0023`,
issue #60) resolves a listing's local authority (`admin_district`,
`admin_district_gss` columns on `listings`) via the same
`app/crime/client.py::lookup_postcode` used for crime baselines — that
function isn't scoped to the crime feature specifically, it's a shared
postcodes.io wrapper. `council_tax_rates` is keyed by GSS code (stable
across a council rename; `council_name` is display-only, never joined on)
and holds per-band (A-H) rates the admin maintains via
`PUT /api/council-tax/{gss_code}` — there's no automatic rate source, this
table is hand-populated. No FK/CHECK constraints on the table deliberately,
so a future rate-table tweak never needs the rebuild-and-swap dance other
migrations in this repo have hit.

## Working in this repo

This is a **public** repository. Never commit real listing data, credentials,
or personal information — `media/`, `*.db`, and `.env` are gitignored for
this reason. **Never push to `origin` without asking the user first, every
time** — a prior approval to push does not carry over to a later commit.
