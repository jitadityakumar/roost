from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.commute.tfl_client import search_stop_points
from app.destinations import backfill_queue, backfill_status, store
from app.listings import store as listings_store

router = APIRouter(prefix="/api/destinations", tags=["destinations"])


def _run_backfill_in_background(destination_id: int) -> None:
    """Hands the backfill to backfill_queue's single global FIFO worker
    rather than spawning a dedicated thread per destination -- several
    destinations backfilling concurrently would each fire real HTTP calls
    against TfL's API at once, all sharing tfl_client.py's single module-
    level throttle. See backfill_queue's module docstring for the full
    reasoning. total is computed here (route
    handler thread) rather than inside the queue so a client polling
    GET .../backfill-status right after this call returns is guaranteed
    to already see 'queued' (or 'running', if the queue was empty),
    never a stale 'done'/'failed' from this destination_id's previous
    run."""
    total = len(listings_store.list_listings())
    backfill_queue.enqueue(destination_id, total)


# Same HH:MM pattern as store._TIME_RE -- enforced here too so a malformed
# time produces FastAPI's own clean 422 instead of falling through to
# store.py's ValueError path (both end up 422, but keeping the shape and
# bounds check at the API boundary means a request that's merely
# out-of-range never depends on getting as far as the store layer).
_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class CreateDestinationRequest(BaseModel):
    name: str
    destination_type: str
    tfl_identifier: str
    station_name: str
    day_of_week: int = Field(ge=0, le=6)
    time: str = Field(pattern=_TIME_PATTERN)


class PatchDestinationRequest(BaseModel):
    name: str | None = None
    destination_type: str | None = None
    tfl_identifier: str | None = None
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
        created = store.create_destination(
            body.name, body.destination_type, body.tfl_identifier, body.station_name, body.day_of_week, body.time
        )
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
    # Any of day_of_week/time/tfl_identifier/enabled changing invalidates every
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
    return search_stop_points(q)
