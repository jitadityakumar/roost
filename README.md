# Roost

Track and evaluate house listings you're considering. Submit a Rightmove URL,
Roost extracts the structured listing data (price, beds/baths, tenure,
stations, broadband, etc.) and tracks it over time as an ongoing shortlist —
not a one-off bookmark.

## Status

**Phase 1** (this build): local-only, no auth. Submit Rightmove URLs, view
extracted listings, edit fields manually, track status (active/in-review).
New listings start in-review; promote to active once you've checked the
data, demote back if needed. No LLM enrichment worker yet (Phase 3) and no
commute/mortgage joins yet (Phase 2) — those show as UI stubs.

## Stack

- Backend: Python (FastAPI) + SQLite
- Frontend: React
- Packaging: single Docker container (backend serves the built frontend as
  static files; SQLite on a mounted volume)

## How it works

Paste a Rightmove URL in and it comes back immediately with a stub card — no
waiting on the scrape. A background job fetches the listing, extracts
structured fields, then queues a media download for the photos, floorplan,
and EPC graphic. The card upgrades in place once that's done. Any field can
be manually corrected afterward; a manual edit sticks and won't be
overwritten by a later refresh.

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

## Running with Docker

```
docker build -t roost .
docker run -d --name roost --restart unless-stopped \
  -p 8099:8000 -v $(pwd)/data:/data \
  --add-host=host.docker.internal:host-gateway \
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
the Phase 3 llm-lane worker deliberately logs full (not truncated) failure
output for diagnosis, so without a cap a long-running container with
recurring llm failures could otherwise accumulate an ever-growing log file
on the host.

The Phase 3 LLM enrichment worker calls a separate, host-resident LLM
bridge (`host/llm_bridge/`) over HTTP instead of shelling out to the
`claude` CLI inside the container — the bridge is what holds the
`claude login` session now, not this container, which no longer touches
`~/.claude` at all. `--add-host=host.docker.internal:host-gateway` plus
`ROOST_LLM_BRIDGE_BASE=http://host.docker.internal:8094` in `.env` is how
the container reaches it. See `host/llm_bridge/README.md` for setting the
bridge up (its own venv + optional systemd unit — a separate, host-level
install step, not part of this `docker build`/`docker run` flow). The
`/data` volume holds the SQLite database and downloaded media so they
survive container restarts.

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
