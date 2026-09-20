from fastapi import APIRouter, HTTPException

from app.crime.client import CrimeApiError, lookup_postcode
from app.listings import store as listings_store
from app.localpolitics import service

router = APIRouter(prefix="/api/listings", tags=["local-politics"])


def _get_listing_or_404(listing_id: int) -> dict:
    listing = listings_store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return listing


@router.get("/{listing_id}/local-politics")
def get_local_politics(listing_id: int):
    return service.section_payload(_get_listing_or_404(listing_id))


@router.post("/{listing_id}/local-politics/refresh")
def refresh_local_politics(listing_id: int):
    """Manual retry of the scrape-time resolve step (postcodes.io fields,
    then the MP row). Never re-downloads the council CSV, and never wipes
    good data on failure: a failed or empty lookup leaves stored values
    untouched and is reported in `refresh` instead. A postcodes.io request
    failure is a 502 (nothing changed); a postcode it doesn't recognise, or
    an MP that can't be found/fetched, is a 200 with refresh.ok=false."""
    listing = _get_listing_or_404(listing_id)
    postcode = listing.get("postcode")
    if not postcode:
        raise HTTPException(status_code=422, detail="listing has no postcode")

    try:
        resolved = lookup_postcode(postcode)
    except CrimeApiError as e:
        raise HTTPException(status_code=502, detail=f"postcode lookup failed: {e}")
    cols = service.columns_from_resolved(resolved)
    if resolved is None:
        message = "postcodes.io didn't recognise this postcode"
        ok = False
    elif not cols["constituency_gss"] or not cols["constituency"]:
        # Don't wipe a stored constituency/MP because this one response
        # lacked it -- leave the constituency-derived columns alone.
        listings_store.apply_extracted_fields(
            listing_id,
            {
                "admin_district": resolved["admin_district"],
                "admin_district_gss": resolved["codes"]["admin_district"],
            },
            from_scrape=False,
        )
        message = "postcodes.io returned no constituency for this postcode"
        ok = False
    else:
        listings_store.apply_extracted_fields(
            listing_id,
            {
                "admin_district": resolved["admin_district"],
                "admin_district_gss": resolved["codes"]["admin_district"],
                **cols,
            },
            from_scrape=False,
        )
        status = service.ensure_mp(cols["constituency_gss"], cols["constituency"], force=True)
        ok = status == "ok"
        message = {
            "ok": None,
            "not_found": "couldn't identify a single MP for this constituency",
            "error": "the Parliament Members API request failed",
        }[status]

    payload = service.section_payload(listings_store.get_listing(listing_id))
    payload["refresh"] = {"ok": ok, "message": message}
    return payload
