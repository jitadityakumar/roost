# Roost

Track and evaluate house listings you're considering. Submit a Rightmove URL,
Roost extracts the structured listing data (price, beds/baths, tenure,
stations, broadband, etc.) and tracks it over time as an ongoing shortlist —
not a one-off bookmark.

## Status

**Phase 1** (this build): local-only, no auth. Submit Rightmove URLs, view
extracted listings, edit fields manually, track status (active/removed/
suspended). No LLM enrichment worker yet (Phase 3) and no commute/mortgage
joins yet (Phase 2) — those show as UI stubs.

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
