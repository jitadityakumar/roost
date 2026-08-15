"""In-memory progress tracking for compute.compute_for_destination's
backfill runs -- see GitHub issue #36.

Deliberately not a DB table: a run's progress is a transient UI nicety
only (the actual journey rows compute_for_destination writes to
destination_journeys are the real data and always correct regardless of
whether this module's state survives), and Roost is a single-user app
where a process restart mid-backfill is an accepted gap -- same tolerance
as an interrupted scrape job today, decided when this feature was
designed rather than building restart-recovery for a rare, self-healing
(next add/edit retriggers a full backfill) case.

Keyed by destination_id, not a single global slot, so two destinations
backfilling in quick succession (e.g. two rapid admin edits) each get
their own tracked run and a poll for one destination's status is never
confused with another's.
"""
from __future__ import annotations

import threading

# compute_for_destination runs inside a worker thread (via
# asyncio.to_thread, called from routes/destinations.py), while the status
# route reads this from the event-loop thread -- a plain lock, not
# sqlite's WAL/busy_timeout story, is what's actually protecting this dict.
_lock = threading.Lock()
_runs: dict[int, dict] = {}


def start(destination_id: int, total: int) -> bool:
    """Begin tracking a new run for this destination. Returns False (and
    leaves the existing entry untouched) if a run for this destination_id
    is already 'running' -- guards against a rapid double-submit (e.g. two
    quick edits before the first backfill finishes) starting two
    overlapping backfills for the same destination."""
    with _lock:
        existing = _runs.get(destination_id)
        if existing is not None and existing["status"] == "running":
            return False
        _runs[destination_id] = {"status": "running", "done": 0, "total": total}
        return True


def increment(destination_id: int) -> None:
    with _lock:
        run = _runs.get(destination_id)
        if run is not None:
            run["done"] += 1


def finish(destination_id: int, status: str) -> None:
    with _lock:
        run = _runs.get(destination_id)
        if run is not None:
            run["status"] = status


def get(destination_id: int) -> dict | None:
    """None means no run has ever been tracked for this destination_id in
    this process's lifetime -- the status route treats that the same as
    'idle', not as an error."""
    with _lock:
        run = _runs.get(destination_id)
        return dict(run) if run is not None else None
