from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.commute.stations import search_stations
from app.destinations import compute, store

router = APIRouter(prefix="/api/destinations", tags=["destinations"])

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
    # Backfills every existing listing synchronously before returning --
    # train-journey-planner is local/free, unlike the Google Maps walking-
    # distance calls that need an opt-out for bulk backfill cost, so there's
    # no reason to make the admin remember a separate backfill step. This
    # does mean the request takes longer (roughly one train-journey-planner
    # round trip per candidate station per listing) -- the frontend shows a
    # loading state on the Add button for exactly this reason.
    try:
        created = store.create_destination(body.name, body.crs, body.station_name, body.day_of_week, body.time)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    compute.compute_for_destination(created["id"])
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
    # specific fields actually changed.
    if changes:
        compute.compute_for_destination(destination_id)
    return updated


@router.delete("/{destination_id}", status_code=204)
def delete_destination(destination_id: int):
    store.delete_destination(destination_id)


@router.get("/stations/search")
def station_search(q: str = ""):
    return search_stations(q)
