# Roost

Track and evaluate house listings you're considering. Submit a Rightmove URL,
Roost extracts the structured listing data (price, beds/baths, tenure,
stations, broadband, etc.) and tracks it over time as an ongoing shortlist —
not a one-off bookmark.

Local-only, no auth, single SQLite file, single Docker container.

## What's implemented

Core (no configuration needed):

- Submit a Rightmove URL, get a stub card back immediately, background job
  scrapes + extracts fields, downloads photos/floorplan/EPC image.
- Manual field editing — an edit sticks and is never overwritten by a later
  refresh/re-scrape.
- Status tracking (in-review / active / rejected) with a comment field.
- Admin-defined "standards" rules (e.g. "floor area < 700 sqft") flagged
  per-listing, purely advisory.

Optional — each needs an external dependency to actually run; without it the
feature is skipped/hidden rather than the app breaking (see
[Requirements](#requirements) below):

- LLM-enriched fields (lease years, service charge, council tax band,
  chain-free, cash-only, floor area/EPC read off images) — needs the `claude`
  CLI + an authenticated session.
- Commute times to configured termini — needs a running
  `london-commuter-stations` sibling service.
- Mortgage-affordability estimate — needs a running `mortgage-calculator`
  sibling service.
- Nearest-station walking distance/time, and "frequent destination" journey
  times (e.g. commute to work) via TfL — needs a free TfL API key.
- Home-vs-listing commute duration comparison — needs your home coordinates.
- Local crime-rate comparison against baseline postcodes, and council tax
  band estimates — needs outbound internet to two free public APIs (no key).

## Requirements

### To run the app at all

- Python 3.12+
- Node.js 20+ (frontend build/dev only — not needed at container runtime)
- Docker, if running via the packaged container (recommended)

### To run every optional feature

None of these are required to start the app — each is independently
optional, checked at call time, and fails soft (the feature reports
"unavailable"/is hidden; nothing else breaks). All are read from environment
variables — see `backend/app/config.py`.

| Feature | Requirement | Env var | If missing |
|---|---|---|---|
| LLM enrichment | `claude` CLI installed + an authenticated session (`claude login`) | — (session mounted from `~/.claude` and `~/.claude.json`, no API key) | `llm`-lane jobs fail with a clear error per job; scraped fields still work |
| Commute times | A running `london-commuter-stations` instance | `ROOST_COMMUTE_API_BASE` | `GET .../commute` raises a `CommuteApiError`; UI shows it as unavailable |
| Mortgage estimate | A running `mortgage-calculator` instance | `ROOST_MORTGAGE_API_BASE` | `GET .../mortgage` returns `{"result": null, "error": "..."}` |
| Station walk distance + frequent destinations | A free TfL Unified API key ([register here](https://api-portal.tfl.gov.uk/)) | `TFL_API_KEY` | Per-station/journey computation is skipped and logged, not fatal; falls back to Rightmove's straight-line distance where applicable |
| Home-vs-listing comparison | Your home's coordinates | `ROOST_HOME_LAT`, `ROOST_HOME_LON` | Comparison is simply not computed/shown |
| Crime comparison + council tax band | None (public, keyless APIs: `api.postcodes.io`, `data.police.uk`) — just outbound internet access from wherever the backend runs | — | Requests to those two hosts fail; the feature errors per-listing |

None of these are secrets you check into the repo — set them via `.env`
(gitignored) and pass with `--env-file` (see [Docker](#running-with-docker)),
or export them in your shell for local dev.

### To run the test suites

- Backend: `backend/requirements-dev.txt` (pytest, httpx) — extra deps on
  top of `requirements.txt`, dev/test only.
- Frontend: already in `frontend/package.json` devDependencies (vitest).
- End-to-end (`e2e/`): Node + `@playwright/test`, and Docker (spins up a
  real container to test against).

## Stack

- Backend: Python (FastAPI) + SQLite
- Frontend: React
- Packaging: single Docker container (backend serves the built frontend as
  static files; SQLite on a mounted volume)

## Development

```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```
cd frontend
npm install
npm run dev
```

Optional feature env vars (see [Requirements](#requirements)) can be
exported in the shell before `uvicorn`/`npm run dev`, or put in a local
`.env` and sourced — there's no built-in dotenv loading in dev, only in the
Docker path below.

## Testing

```
scripts/test.sh
```

Runs the backend pytest suite (`backend/tests/`) and frontend vitest suite
(`frontend/src/tests/`) — the fast local checks to run after every change.
Installs `backend/requirements-dev.txt` into `backend/.venv` automatically.
Neither suite talks to Rightmove or any of the optional external services
above; they run entirely against fixtures/mocks.

```
scripts/e2e.sh
```

Builds the Docker image, runs a throwaway container on a separate port with
a temp data directory, runs the Playwright suite in `e2e/` against it, then
tears the container down. Requires Docker. Slower and more involved than
`test.sh` — run it before a release, not on every change.

## Running with Docker

```
docker build -t roost .
docker run -d --name roost --restart unless-stopped \
  -p 8099:8000 -v $(pwd)/data:/data \
  -v ~/.claude:/root/.claude:ro \
  -v ~/.claude.json:/root/.claude.json:ro \
  --env-file .env \
  --log-opt max-size=10m --log-opt max-file=3 roost
```

Then open http://localhost:8099. Port 8099 (not 8000) is used on the host
because 8000 is already taken by `mortgage-calculator` on this machine.
`--restart unless-stopped` makes the container come back up automatically
after a reboot or Docker restart, as long as you didn't stop it manually.
`--log-opt max-size=10m --log-opt max-file=3` caps Docker's default
`json-file` log driver at 3 rotated 10MB files (~30MB total) instead of
growing unbounded — the app logs to stdout only (`docker logs roost`), and
the llm-lane worker deliberately logs full (not truncated) failure output
for diagnosis, so without a cap a long-running container with recurring llm
failures could otherwise accumulate an ever-growing log file on the host.

`--env-file .env` is how every optional feature in the
[Requirements](#requirements) table above gets configured — a `.env` file
(gitignored, not tracked in this repo) holding whichever of
`ROOST_COMMUTE_API_BASE`, `ROOST_MORTGAGE_API_BASE`, `TFL_API_KEY`,
`ROOST_HOME_LAT`/`ROOST_HOME_LON` you want enabled. Any left unset just
means that one feature is unavailable — the app runs fine without any of
them. `--env-file` is used deliberately instead of inline `-e`/python-dotenv,
since inline flags leave the value visible in shell history / `ps aux`.

The `-v ~/.claude:/root/.claude:ro` and `-v ~/.claude.json:/root/.claude.json:ro`
mounts give the LLM enrichment worker read-only access to the host's
existing `claude login` session (the second file is separate, home-root
onboarding/trust state the CLI also expects), so no separate API key needs
to be provisioned or stored in the container. If you don't want LLM
enrichment, omit both mounts — those jobs will just fail with a clear
"claude CLI not found"/auth error and every other feature is unaffected.
Known tradeoff of the `:ro` mounts: the CLI can't persist a refreshed OAuth
token back to the host, so if `llm`-lane jobs start failing with an auth
error after the container's been running a long time, re-running
`claude login` on the host (which the container will pick up on its next
call, since the mount is live) is the fix. The `/data` volume holds the
SQLite database and downloaded media so they survive container restarts.

## Data

Extracted listing media (photos/floorplans/EPC graphics) and the SQLite
database are stored locally under `backend/data/` (gitignored) — never
committed to this public repo.

## Backup

A simple periodic copy of the database and media directory to a second
location:

```
cd backend
python3 -m app.backup
```

Writes a timestamped snapshot to `../backups/` (override with
`ROOST_BACKUP_DIR`), keeping the last 7. Run it via cron for actual periodic
backups — nothing schedules it automatically yet.

## Scripts

All in `scripts/`, run from the repo root:

| Script | Purpose |
|---|---|
| `test.sh` | Backend pytest + frontend vitest (see [Testing](#testing)) |
| `e2e.sh` | Playwright e2e suite against a throwaway Docker container |
| `backfill-rightmove.sh` | Re-run Rightmove extraction across existing listings; `--skip-llm` opts out of the LLM-lane chain (see `CLAUDE.md`) |
| `backfill-llm.sh` | Re-run the LLM-lane jobs (text/vision extraction) across existing listings |
| `tfl-walk-backfill.sh` | Recompute nearest-station walking distance/time for existing listings without a full re-scrape |
| `destinations-backfill.sh` | Recompute frequent-destination journey times for existing listings |
| `crime-backfill.sh` | Refresh cached crime stats for baseline/listing postcodes |
