from fastapi import APIRouter, HTTPException

from app.listings import store
from app.listings.serialize import serialize_listing
from app.mortgage.client import MortgageApiError, fetch_mortgage_calculation

router = APIRouter(prefix="/api/listings", tags=["mortgage"])


@router.get("/{listing_id}/mortgage")
def get_mortgage(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    serialized = serialize_listing(listing)
    price_gbp = serialized.get("price_gbp")
    if price_gbp is None:
        return {"result": None, "error": "listing has no price"}

    service_charge_pm = serialized.get("service_charge_pm")
    try:
        result = fetch_mortgage_calculation(price_gbp, service_charge_pm)
        return {"result": result, "error": None}
    except MortgageApiError as e:
        return {"result": None, "error": str(e)}
