from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.commute.stations import search_stations
from app.destinations import store

router = APIRouter(prefix="/api/destinations", tags=["destinations"])


class CreateDestinationRequest(BaseModel):
    name: str
    crs: str
    station_name: str
    day_of_week: int
    time: str


class PatchDestinationRequest(BaseModel):
    name: str | None = None
    crs: str | None = None
    station_name: str | None = None
    day_of_week: int | None = None
    time: str | None = None
    enabled: bool | None = None


@router.get("")
def list_destinations():
    return store.list_destinations()


@router.post("", status_code=201)
def create_destination(body: CreateDestinationRequest):
    try:
        return store.create_destination(body.name, body.crs, body.station_name, body.day_of_week, body.time)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{destination_id}")
def patch_destination(destination_id: int, body: PatchDestinationRequest):
    changes = body.model_dump(exclude_unset=True)
    try:
        updated = store.update_destination(destination_id, **changes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="destination not found")
    return updated


@router.delete("/{destination_id}", status_code=204)
def delete_destination(destination_id: int):
    store.delete_destination(destination_id)


@router.get("/stations/search")
def station_search(q: str = ""):
    return search_stations(q)
