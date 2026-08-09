import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import MEDIA_DIR
from app.jobs import llm_enqueue, queue
from app.jobs.pipeline_status import derive_pipeline_status
from app.listings import store, url_utils
from app.listings.serialize import serialize_listing
from app.standards import store as standards_store
from app.standards.evaluate import evaluate_listing

router = APIRouter(prefix="/api/listings", tags=["listings"])


def _serialize_with_pipeline_status(listing: dict) -> dict:
    statuses = queue.latest_job_statuses_for_listings([listing["id"]])
    out = serialize_listing(listing)
    out["pipeline_status"] = derive_pipeline_status(statuses.get(listing["id"], {}))
    return out


def _serialize_many_with_pipeline_status(listings: list[dict]) -> list[dict]:
    statuses = queue.latest_job_statuses_for_listings([l["id"] for l in listings])
    result = []
    for listing in listings:
        out = serialize_listing(listing)
        out["pipeline_status"] = derive_pipeline_status(statuses.get(listing["id"], {}))
        result.append(out)
    return result

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


VALID_USER_STATUSES = ("triage", "approved", "rejected")


class PatchListingRequest(BaseModel):
    user_status: str | None = None
    rejection_reason: str | None = None
    comment: str | None = None
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
    return _serialize_with_pipeline_status(store.get_listing(property_id))


@router.get("")
def list_listings(user_status: str | None = None):
    return _serialize_many_with_pipeline_status(store.list_listings(user_status))


@router.get("/{listing_id}")
def get_listing(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    out = _serialize_with_pipeline_status(listing)
    out["standards_violations"] = evaluate_listing(listing, standards_store.list_rules())
    return out


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
    return _serialize_with_pipeline_status(store.get_listing(listing_id))


@router.post("/{listing_id}/llm-refresh", status_code=202)
def llm_refresh_listing(listing_id: int):
    """Re-runs the llm-lane jobs (text_extract, floor_area_vision,
    epc_vision) directly, without re-scraping Rightmove first — unlike
    /refresh, which re-runs the whole chain. Meant for backfilling existing
    listings after a model/prompt/schema change (see scripts/backfill-llm.sh)
    where the underlying Rightmove data and downloaded images haven't
    changed, only how we read them.

    Reuses the exact same should_enqueue/first_media_file guards the normal
    rightmove_extract/media_download auto-chain already applies (see
    handlers.py) — a hand-edited field stays hand-edited (should_enqueue's
    stickiness check), and a vision job with no image on disk is silently
    skipped rather than enqueued to fail. Not gated on any field already
    being llm-sourced — a backfill's entire point is to overwrite a prior
    llm-sourced value with a fresh one, and a rightmove-sourced field is
    protected separately (each handler checks its own `_source` column
    before writing, same protection /refresh relies on)."""
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    enqueued = []
    if llm_enqueue.should_enqueue(listing_id, "text_extract"):
        queue.enqueue_job(listing_id, "text_extract", "llm")
        enqueued.append("text_extract")
    if llm_enqueue.should_enqueue(listing_id, "floor_area_vision") and llm_enqueue.first_media_file(
        listing_id, "floorplans"
    ):
        queue.enqueue_job(listing_id, "floor_area_vision", "llm")
        enqueued.append("floor_area_vision")
    if llm_enqueue.should_enqueue(listing_id, "epc_vision") and llm_enqueue.first_media_file(listing_id, "epc"):
        queue.enqueue_job(listing_id, "epc_vision", "llm")
        enqueued.append("epc_vision")
    return {"enqueued": enqueued}


@router.patch("/{listing_id}")
def patch_listing(listing_id: int, body: PatchListingRequest):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    if body.user_status is not None:
        if body.user_status not in VALID_USER_STATUSES:
            raise HTTPException(status_code=422, detail="invalid user_status")
        if body.user_status == "rejected":
            if not body.rejection_reason or not body.rejection_reason.strip():
                raise HTTPException(status_code=422, detail="rejection_reason is required when rejecting")
            store.set_user_status(listing_id, body.user_status, rejection_reason=body.rejection_reason.strip())
        else:
            store.set_user_status(listing_id, body.user_status)

    if body.comment is not None:
        store.set_comment(listing_id, body.comment.strip() or None)

    if body.fields:
        unknown = set(body.fields) - EDITABLE_FIELDS
        if unknown:
            raise HTTPException(status_code=422, detail=f"non-editable field(s): {sorted(unknown)}")
        store.apply_manual_edit(listing_id, body.fields)

    return _serialize_with_pipeline_status(store.get_listing(listing_id))


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
