import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import MEDIA_DIR
from app.jobs import queue
from app.listings import store, url_utils
from app.listings.serialize import serialize_listing

router = APIRouter(prefix="/api/listings", tags=["listings"])

# Editable via PATCH's manual-edit path — anything not on this list (system
# columns like extraction_status, id, url, created_at) is rejected.
EDITABLE_FIELDS = {
    "price_gbp", "address", "postcode", "property_type", "bedrooms", "bathrooms",
    "tenure", "description", "agent_branch", "agent_address",
    "lease_years_remaining", "service_charge_pa", "service_charge_pm",
    "council_tax_band", "floor_area_sqft", "epc_current", "epc_potential",
    "chain_free", "cash_only", "garden", "parking",
}


class CreateListingRequest(BaseModel):
    url: str


class PatchListingRequest(BaseModel):
    user_status: str | None = None
    fields: dict | None = None


@router.post("", status_code=201)
def create_listing(body: CreateListingRequest):
    try:
        property_id = url_utils.extract_property_id(body.url)
    except url_utils.InvalidListingUrlError as e:
        raise HTTPException(status_code=422, detail=str(e))

    canonical = url_utils.canonical_url(property_id)
    # create_stub_listing is the atomic operation (INSERT ... ON CONFLICT DO
    # NOTHING) — its return value tells us whether *this* request was the one
    # that actually created the row. A preceding get_listing()-then-insert
    # check would leave a race window where two concurrent submissions of a
    # brand-new URL both see "doesn't exist yet" and both enqueue an
    # extraction job for it.
    inserted = store.create_stub_listing(property_id, canonical)
    if inserted:
        queue.enqueue_job(property_id, "rightmove_extract", "http")
    return serialize_listing(store.get_listing(property_id))


@router.get("")
def list_listings(user_status: str | None = None):
    return [serialize_listing(l) for l in store.list_listings(user_status)]


@router.get("/{listing_id}")
def get_listing(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return serialize_listing(listing)


@router.post("/{listing_id}/refresh", status_code=202)
def refresh_listing(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    # Without this guard, N rapid clicks on refresh enqueue N extraction
    # jobs for the same listing (each producing its own snapshot row and
    # media_download job) instead of just riding the one already in flight.
    if not queue.has_pending_job(listing_id, "rightmove_extract"):
        store.set_extraction_status(listing_id, "queued")
        queue.enqueue_job(listing_id, "rightmove_extract", "http")
    return serialize_listing(store.get_listing(listing_id))


@router.patch("/{listing_id}")
def patch_listing(listing_id: int, body: PatchListingRequest):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    if body.user_status is not None:
        if body.user_status not in ("active", "in_review"):
            raise HTTPException(status_code=422, detail="invalid user_status")
        store.set_user_status(listing_id, body.user_status)

    if body.fields:
        unknown = set(body.fields) - EDITABLE_FIELDS
        if unknown:
            raise HTTPException(status_code=422, detail=f"non-editable field(s): {sorted(unknown)}")
        store.apply_manual_edit(listing_id, body.fields)

    return serialize_listing(store.get_listing(listing_id))


@router.delete("/{listing_id}", status_code=204)
def delete_listing(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    store.delete_listing(listing_id)
    media_dir = f"{MEDIA_DIR}/{listing_id}"
    shutil.rmtree(media_dir, ignore_errors=True)


@router.get("/{listing_id}/jobs")
def get_jobs(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return queue.get_jobs_for_listing(listing_id)
