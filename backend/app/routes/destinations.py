import threading
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.commute.stations import search_stations
from app.destinations import backfill_status, compute, store
from app.listings import store as listings_store

router = APIRouter(prefix="/api/destinations", tags=["destinations"])

# Test-only visibility hook: conftest.py's isolated_db fixture joins every
# thread in here before the next test repoints ROOST_DB_PATH, so a slow
# backfill from one test can never run against a different test's (or an
# unmigrated) SQLite file. Pruned of finished threads on every append (see
# _track_background_thread) so this doesn't grow unboundedly across the
# life of a real running process, which never joins it.
_background_threads: list[threading.Thread] = []

# destination_ids with a rerun already queued behind their current backfill
# -- see _run_backfill_in_background's "already running" branch. Guarded by
# the same lock backfill_status uses internally would be overkill here;
# this set is only ever touched from route-handler threads (FastAPI's
# threadpool), never from a backfill thread itself, so a plain lock is
# enough.
_pending_reruns: set[int] = set()
_pending_reruns_lock = threading.Lock()


def _track_background_thread(thread: threading.Thread) -> None:
    _background_threads[:] = [t for t in _background_threads if t.is_alive()]
    _background_threads.append(thread)


def _run_backfill_in_background(destination_id: int) -> None:
    # backfill_status.start() runs synchronously, here, before the request
    # returns -- not inside the background thread -- so a client polling
    # GET .../backfill-status right after create/edit responds is
    # guaranteed to already see 'running', never a stale 'done' left over
    # from this destination_id's previous run.
    total = len(listings_store.list_listings())
    if backfill_status.start(destination_id, total=total):
        # Every route in this file is a plain sync `def` (FastAPI runs those
        # in its threadpool, with no event loop bound to that worker
        # thread), so there's no asyncio loop here to hand a task to -- a
        # plain daemon thread is the simplest fire-and-forget mechanism
        # available without converting these routes to async just for this.
        # compute_for_destination itself reports incremental progress via
        # backfill_status as it goes.
        thread = threading.Thread(target=compute.compute_for_destination, args=(destination_id,), daemon=True)
        _track_background_thread(thread)
        thread.start()
        return

    # A backfill for this destination_id is already running. Dropping this
    # request outright would silently lose it -- e.g. two edits to the same
    # destination arriving close together, where the second must still take
    # effect once the first backfill finishes, not vanish. Queue exactly one
    # rerun (further calls while one's already queued are no-ops, since
    # compute_for_destination always re-reads the destination's current row
    # when it eventually runs, so a rerun triggered by *any* of several
    # rapid edits ends up reflecting whichever edit was last by the time it
    # actually runs).
    with _pending_reruns_lock:
        if destination_id in _pending_reruns:
            return
        _pending_reruns.add(destination_id)

    def _wait_then_rerun():
        while True:
            status = backfill_status.get(destination_id)
            if status is None or status["status"] != "running":
                break
            time.sleep(0.2)
        with _pending_reruns_lock:
            _pending_reruns.discard(destination_id)
        _run_backfill_in_background(destination_id)

    waiter = threading.Thread(target=_wait_then_rerun, daemon=True)
    _track_background_thread(waiter)
    waiter.start()


# Same HH:MM pattern as store._TIME_RE -- enforced here too so a malformed
# time produces FastAPI's own clean 422 instead of falling through to
# store.py's ValueError path (both end up 422, but keeping the shape and
# bounds check at the API boundary means a request that's merely
# out-of-range never depends on getting as far as the store layer).
_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class CreateDestinationRequest(BaseModel):
    name: str
    crs: str
    station_name: str
    day_of_week: int = Field(ge=0, le=6)
    time: str = Field(pattern=_TIME_PATTERN)


class PatchDestinationRequest(BaseModel):
    name: str | None = None
    crs: str | None = None
    station_name: str | None = None
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    time: str | None = Field(default=None, pattern=_TIME_PATTERN)
    enabled: bool | None = None


@router.get("")
def list_destinations():
    return store.list_destinations()


@router.post("", status_code=201)
def create_destination(body: CreateDestinationRequest):
    # Backfills every existing listing in the background (issue #36) --
    # train-journey-planner is local/free, unlike the Google Maps walking-
    # distance calls that need an opt-out for bulk backfill cost, so there's
    # no reason to make the admin remember a separate backfill step. The
    # request itself returns as soon as the destination row exists; the
    # frontend polls GET .../{id}/backfill-status for progress instead of
    # blocking on the whole backfill.
    try:
        created = store.create_destination(body.name, body.crs, body.station_name, body.day_of_week, body.time)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _run_backfill_in_background(created["id"])
    return created


@router.patch("/{destination_id}")
def patch_destination(destination_id: int, body: PatchDestinationRequest):
    changes = body.model_dump(exclude_unset=True)
    try:
        updated = store.update_destination(destination_id, **changes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="destination not found")
    # Any of day_of_week/time/crs/enabled changing invalidates every
    # existing listing's stored journey for this destination -- simplest
    # correct behavior is to always recompute rather than tracking which
    # specific fields actually changed. Backgrounded the same way as create.
    if changes:
        _run_backfill_in_background(destination_id)
    return updated


@router.delete("/{destination_id}", status_code=204)
def delete_destination(destination_id: int):
    store.delete_destination(destination_id)


@router.get("/{destination_id}/backfill-status")
def get_backfill_status(destination_id: int):
    """Polled by the admin page while a create/edit backfill runs. No
    tracked run (never started in this process's lifetime, or this
    destination_id doesn't exist) reads the same as 'idle' -- there's
    nothing for the frontend to distinguish there, since either way there's
    no progress bar to show."""
    status = backfill_status.get(destination_id)
    if status is None:
        return {"status": "idle", "done": 0, "total": 0}
    return status


@router.get("/stations/search")
def station_search(q: str = ""):
    return search_stations(q)
