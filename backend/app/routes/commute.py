from fastapi import APIRouter, HTTPException

from app.commute.client import CommuteApiError, fetch_station_termini
from app.commute.stations import latlong_for_crs, resolve_crs_codes
from app.commute.walk_store import get_walk_distances
from app.listings import store
from app.listings.serialize import serialize_listing

router = APIRouter(prefix="/api/listings", tags=["commute"])


def _maps_walking_url(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> str:
    return (
        f"https://www.google.com/maps/dir/?api=1&origin={origin_lat},{origin_lon}"
        f"&destination={dest_lat},{dest_lon}&travelmode=walking"
    )


@router.get("/{listing_id}/commute")
def get_commute(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    serialized = serialize_listing(listing)
    nearest_stations_raw = serialized.get("nearest_stations_raw") or []
    origin_lat, origin_lon = serialized.get("latitude"), serialized.get("longitude")
    walk_distances = get_walk_distances(listing_id)

    stations = []
    for station in resolve_crs_codes(nearest_stations_raw):
        result = dict(station)
        try:
            result["termini"] = fetch_station_termini(station["crs"])
            result["error"] = None
        except CommuteApiError as e:
            result["termini"] = None
            result["error"] = str(e)

        walk = walk_distances.get(station["crs"])
        result["walk_distance_meters"] = walk["distance_meters"] if walk else None
        result["walk_duration_seconds"] = walk["duration_seconds"] if walk else None
        result["walk_maps_url"] = None
        if origin_lat is not None and origin_lon is not None:
            dest_latlong = latlong_for_crs(station["crs"])
            if dest_latlong is not None:
                result["walk_maps_url"] = _maps_walking_url(origin_lat, origin_lon, *dest_latlong)

        stations.append(result)
    return {"stations": stations}
