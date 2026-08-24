from fastapi import APIRouter, HTTPException

from app.destinations import compute, journey_store, store
from app.listings import store as listings_store
from app.listings.serialize import serialize_listing

router = APIRouter(prefix="/api/listings", tags=["destinations"])

_DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _serialize(destination: dict, journeys: dict, home_journeys: dict, scan_pool_info: dict) -> dict:
    journey = journeys.get(destination["id"])
    info = scan_pool_info.get(destination["id"])
    out = {
        "destination_id": destination["id"],
        "name": destination["name"],
        "destination_type": destination["destination_type"],
        "station_name": destination["station_name"],
        "day_of_week": destination["day_of_week"],
        "day_label": _DAY_LABELS[destination["day_of_week"]],
        "time": destination["time"],
        "resolved": journey is not None,
    }
    if journey:
        out.update(
            {
                "duration_minutes": journey["duration_minutes"],
                "kind": journey["kind"],
                "num_changes": journey["num_changes"],
                "operator": journey["operator"],
                "origin_crs": journey["origin_crs"],
                "origin_name": journey["origin_name"],
                "arrival_name": journey["arrival_name"],
                "interchange_crs": journey["interchange_crs"],
                "departure_time": journey["departure_time"],
                "arrival_time": journey["arrival_time"],
                "computed_at": journey["computed_at"],
                "journey_scan_pool_id": info["id"] if info is not None else None,
            }
        )
        # Issue #67: whole-window, ungrouped candidate count (not just ones
        # matching this journey's specific route) -- deliberately not
        # grouped by route, per investigation against live
        # journey_scan_pools data: alternative routes TfL finds within the
        # window are consistently close in duration/num_changes to each
        # other, so lumping them into one count matches how a rider would
        # actually experience "how often can I make this trip". See
        # journey_store.frequency_per_hour for the count->rate formula.
        # Omitted entirely (unlike journey_scan_pool_id, which is always
        # present as None) when no pool was captured for this destination
        # (e.g. the HUB best_pool edge case documented in tfl_client.py) --
        # matches how the frontend already treats a missing field.
        if info is not None:
            out["frequency_per_hour"] = info["frequency_per_hour"]
        # Live diff, not stored -- computed fresh from each side's own
        # duration_minutes every request, so it's never stale relative to
        # either. Omitted entirely (not even a null key) if either side has
        # no result -- no home configured (config.HOME_LAT/LON unset, see
        # compute.py), or this destination's home journey/this listing's
        # journey wasn't found. Positive means this listing's journey is
        # slower than the trip from home.
        home_journey = home_journeys.get(destination["id"])
        if home_journey is not None:
            out["home_duration_diff_minutes"] = journey["duration_minutes"] - home_journey["duration_minutes"]
    return out


def _listing_or_404(listing_id: int) -> dict:
    listing = listings_store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return listing


@router.get("/{listing_id}/destinations")
def get_destinations(listing_id: int):
    _listing_or_404(listing_id)
    journeys = journey_store.get_journeys(listing_id)
    home_journeys = journey_store.get_home_journeys()
    scan_pool_info = journey_store.get_scan_pool_info(listing_id)
    return [
        _serialize(d, journeys, home_journeys, scan_pool_info) for d in store.list_destinations() if d["enabled"]
    ]


@router.post("/{listing_id}/destinations/refresh", status_code=202)
def refresh_destinations(listing_id: int):
    listing = _listing_or_404(listing_id)
    serialized = serialize_listing(listing)
    compute.compute_for_listing(listing_id, serialized.get("latitude"), serialized.get("longitude"))
    journeys = journey_store.get_journeys(listing_id)
    home_journeys = journey_store.get_home_journeys()
    scan_pool_info = journey_store.get_scan_pool_info(listing_id)
    return [
        _serialize(d, journeys, home_journeys, scan_pool_info) for d in store.list_destinations() if d["enabled"]
    ]
