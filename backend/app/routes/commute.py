from fastapi import APIRouter, HTTPException

from app.commute.client import CommuteApiError, fetch_station_termini
from app.commute.stations import latlong_for_crs, resolve_crs_codes
from app.commute.walk_store import get_walk_distances
from app.listings import store
from app.listings.serialize import serialize_listing

router = APIRouter(prefix="/api/listings", tags=["commute"])

# Stations are resolved up to a 1mi radius (stations.MAX_DISTANCE_MILES) so
# walking distance can be computed for all of them, but the Commute section
# itself should only show/fetch commute data for stations that are actually
# a reasonable walk. A stored walk duration is authoritative; if the Maps
# call failed and we have no stored duration, fall back to Rightmove's raw
# straight-line distance at the old 0.5mi cutoff (a station that far out and
# unmeasurable isn't worth guessing about).
COMMUTE_MAX_WALK_SECONDS = 30 * 60
COMMUTE_FALLBACK_MAX_MILES = 0.5


def _worth_showing_commute(station: dict, walk: dict | None) -> bool:
    if walk and walk["duration_seconds"] is not None:
        return walk["duration_seconds"] <= COMMUTE_MAX_WALK_SECONDS
    distance = station.get("distance")
    return distance is not None and distance <= COMMUTE_FALLBACK_MAX_MILES


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
        walk = walk_distances.get(station["crs"])
        if not _worth_showing_commute(station, walk):
            continue

        result = dict(station)
        try:
            result["termini"] = fetch_station_termini(station["crs"])
            result["error"] = None
        except CommuteApiError as e:
            result["termini"] = None
            result["error"] = str(e)

        result["walk_distance_meters"] = walk["distance_meters"] if walk else None
        result["walk_duration_seconds"] = walk["duration_seconds"] if walk else None
        result["walk_maps_url"] = None
        if origin_lat is not None and origin_lon is not None:
            dest_latlong = latlong_for_crs(station["crs"])
            if dest_latlong is not None:
                result["walk_maps_url"] = _maps_walking_url(origin_lat, origin_lon, *dest_latlong)

        stations.append(result)
    return {"stations": stations}
