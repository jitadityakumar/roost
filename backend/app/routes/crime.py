from fastapi import APIRouter, HTTPException

from app.crime import score, service, store
from app.crime.client import CrimeApiError
from app.listings import store as listings_store
from app.listings.serialize import serialize_listing

router = APIRouter(prefix="/api/listings", tags=["crime"])


@router.get("/{listing_id}/crime")
def get_crime(listing_id: int):
    listing = listings_store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    postcode = serialize_listing(listing).get("postcode")
    if not postcode:
        return {"unavailable": "listing has no postcode", "baselines": []}

    try:
        listing_stats = service.get_or_refresh_stats(postcode)
    except CrimeApiError as e:
        return {"unavailable": str(e), "baselines": []}

    baselines = []
    for baseline in store.list_baselines():
        entry = {"id": baseline["id"], "label": baseline["label"], "postcode": baseline["postcode"]}
        try:
            baseline_stats = service.get_or_refresh_stats(baseline["postcode"])
            entry["comparison"] = score.compare(
                listing_stats["category_counts"], baseline_stats["category_counts"]
            )
            entry["error"] = None
        except CrimeApiError as e:
            entry["comparison"] = None
            entry["error"] = str(e)
        baselines.append(entry)

    return {"unavailable": None, "postcode": postcode, "baselines": baselines}
