from fastapi import APIRouter, HTTPException

from app.commute.client import CommuteApiError, fetch_station_termini
from app.commute.stations import resolve_crs_codes
from app.listings import store
from app.listings.serialize import serialize_listing

router = APIRouter(prefix="/api/listings", tags=["commute"])


@router.get("/{listing_id}/commute")
def get_commute(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    nearest_stations_raw = serialize_listing(listing).get("nearest_stations_raw") or []
    stations = []
    for station in resolve_crs_codes(nearest_stations_raw):
        result = dict(station)
        try:
            result["termini"] = fetch_station_termini(station["crs"])
            result["error"] = None
        except CommuteApiError as e:
            result["termini"] = None
            result["error"] = str(e)
        stations.append(result)
    return {"stations": stations}
