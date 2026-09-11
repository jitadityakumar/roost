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


def _dump_rooms(rooms: list[Room]) -> list[dict]:
    return [r.model_dump() for r in rooms]


def _dump_shapes(shapes: list[Shape]) -> list[dict]:
    return [s.model_dump() for s in shapes]


@router.get("/admin/floorplan-baseline")
def get_baseline():
    return store.get_baseline()


@router.put("/admin/floorplan-baseline")
def put_baseline(body: PutBaselineRequest):
    _validate_room_types(body.rooms)
    return store.put_baseline(
        body.image_blob, body.image_w, body.image_h, body.active_scale,
        _dump_rooms(body.rooms), _dump_shapes(body.shapes),
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
    _validate_room_types(body.rooms)
    return store.put_listing_trace(
        listing_id, body.image_path, body.image_w, body.image_h, body.active_scale,
        _dump_rooms(body.rooms), _dump_shapes(body.shapes),
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
    )
    result["baseline_has_shapes"] = bool(baseline["shapes"])
    result["trace_image_path"] = trace["image_path"]
    return result
