from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.floorplan import compare as compare_mod
from app.floorplan import store
from app.listings import store as listings_store

router = APIRouter(prefix="/api", tags=["floorplan"])

ROOM_TYPE_KEYS = set(compare_mod.ROOM_TYPES)


class Point(BaseModel):
    x: float
    y: float


class Room(BaseModel):
    id: str
    name: str
    color: str
    type: str


class Shape(BaseModel):
    id: str
    roomId: str
    points: list[Point]
    pxArea: float
    scalePxPerFt: float | None = None
    kind: str


class PutBaselineRequest(BaseModel):
    image_blob: str | None = None
    image_w: int | None = None
    image_h: int | None = None
    active_scale: float | None = None
    internal_sqft: float | None = None
    rooms: list[Room]
    shapes: list[Shape]


class PutListingTraceRequest(BaseModel):
    image_path: str
    image_w: int | None = None
    image_h: int | None = None
    active_scale: float | None = None
    rooms: list[Room]
    shapes: list[Shape]


def _validate_room_types(rooms: list[Room]) -> None:
    bad = [r.type for r in rooms if r.type not in ROOM_TYPE_KEYS]
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown room type(s): {sorted(set(bad))}")


# hallway_storage was a traceable room type before it became a computed
# remainder (see compare.py) -- a baseline/trace saved with the old tracer
# button can still have rooms of this type sitting in storage. Rather than
# 422ing the very next save of that row (a confusing failure disconnected
# from whatever the user actually changed), silently drop them: unlike a
# genuinely unknown type (a typo, bad API input), this one has a known,
# intentional meaning -- "no longer traced, now derived automatically".
_LEGACY_ROOM_TYPES = {"hallway_storage"}


def _drop_legacy_rooms(rooms: list[Room], shapes: list[Shape]) -> tuple[list[Room], list[Shape]]:
    kept_rooms = [r for r in rooms if r.type not in _LEGACY_ROOM_TYPES]
    kept_ids = {r.id for r in kept_rooms}
    kept_shapes = [s for s in shapes if s.roomId in kept_ids]
    return kept_rooms, kept_shapes


def _dump_rooms(rooms: list[Room]) -> list[dict]:
    return [r.model_dump() for r in rooms]


def _dump_shapes(shapes: list[Shape]) -> list[dict]:
    return [s.model_dump() for s in shapes]


@router.get("/admin/floorplan-baseline")
def get_baseline():
    return store.get_baseline()


@router.put("/admin/floorplan-baseline")
def put_baseline(body: PutBaselineRequest):
    rooms, shapes = _drop_legacy_rooms(body.rooms, body.shapes)
    _validate_room_types(rooms)
    return store.put_baseline(
        body.image_blob, body.image_w, body.image_h, body.active_scale,
        _dump_rooms(rooms), _dump_shapes(shapes), body.internal_sqft,
    )


@router.get("/listings/{listing_id}/floorplan-trace")
def get_listing_trace(listing_id: int, image_path: str = Query(...)):
    if listings_store.get_listing(listing_id) is None:
        raise HTTPException(status_code=404, detail="listing not found")
    trace = store.get_listing_trace(listing_id, image_path)
    if trace is None:
        raise HTTPException(status_code=404, detail="no trace for this image yet")
    return trace


@router.put("/listings/{listing_id}/floorplan-trace")
def put_listing_trace(listing_id: int, body: PutListingTraceRequest):
    if listings_store.get_listing(listing_id) is None:
        raise HTTPException(status_code=404, detail="listing not found")
    rooms, shapes = _drop_legacy_rooms(body.rooms, body.shapes)
    _validate_room_types(rooms)
    return store.put_listing_trace(
        listing_id, body.image_path, body.image_w, body.image_h, body.active_scale,
        _dump_rooms(rooms), _dump_shapes(shapes),
    )


@router.get("/listings/{listing_id}/floorplan-comparison")
def get_floorplan_comparison(listing_id: int):
    listing = listings_store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    trace = store.get_active_trace(listing_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="no trace with shapes for this listing yet")

    baseline = store.get_baseline()
    result = compare_mod.compare(
        baseline["rooms"], baseline["shapes"],
        trace["rooms"], trace["shapes"],
        listing_floor_area_sqft=listing.get("floor_area_sqft"),
        baseline_internal_sqft=baseline.get("internal_sqft"),
    )
    result["baseline_has_shapes"] = bool(baseline["shapes"])
    result["trace_image_path"] = trace["image_path"]
    return result
