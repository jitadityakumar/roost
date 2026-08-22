import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import MEDIA_DIR
from app.commute.walk_store import get_walk_distances, lookup_walk
from app.counciltax import store as counciltax_store
from app.crime.client import lookup_postcode
from app.jobs import llm_enqueue, queue
from app.jobs.handlers import compute_station_walk_distances
from app.jobs.pipeline_status import derive_pipeline_status
from app.listings import store, url_utils
from app.listings.serialize import serialize_listing
from app.standards import store as standards_store
from app.standards.evaluate import evaluate_listing

router = APIRouter(prefix="/api/listings", tags=["listings"])


def _attach_walk_data(listing_id: int, out: dict) -> None:
    """Attach stored walk_distance_meters/walk_duration_seconds onto each
    nearest_stations_raw entry (unfiltered top-3, straight-line distance, any
    mode -- issue #40 PR2 dropped the old national-rail/1mi computation
    scope) so NearestStations can show real walk figures alongside it for
    whichever entries we happen to have computed walk data for -- see
    context.md's "Station walking distance" section. Runs on every
    single-listing response (`_serialize_with_pipeline_status`, used by
    GET/POST/PATCH on one listing), never on the list endpoint
    (`_serialize_many_with_pipeline_status`) -- walk data is comparatively
    expensive to attach for every card on the hot list path. One
    consequence: the list endpoint's `has_warning` flag (below) can't catch
    a `min_walk_minutes` rule violation, since that field is only computed
    from this attached walk data -- a listing failing only that rule shows
    no warning dot until its detail page is opened.

    Looks up by the entry's position in `nearest_stations_raw` (station_walk_
    distances is index-keyed, not CRS-keyed -- tube/tram/DLR/overground
    stations have no CRS at all), via lookup_walk()'s rightmove_name-match
    guard against a stale row surviving a Rightmove reorder between scrapes.
    get_listing's min_walk_minutes standards field reads the already-guarded
    walk_duration_seconds values this loop attaches, rather than querying
    station_walk_distances again directly -- reading the raw table would
    bypass this same stale-row guard."""
    nearest = out.get("nearest_stations_raw")
    if not isinstance(nearest, list) or not nearest:
        return
    walk_distances = get_walk_distances(listing_id)
    for index, entry in enumerate(nearest):
        walk = lookup_walk(walk_distances, index, entry.get("name", ""))
        entry["walk_distance_meters"] = walk["distance_meters"] if walk else None
        entry["walk_duration_seconds"] = walk["duration_seconds"] if walk else None


def _serialize_with_pipeline_status(listing: dict) -> dict:
    statuses = queue.latest_job_statuses_for_listings([listing["id"]])
    out = serialize_listing(listing)
    out["pipeline_status"] = derive_pipeline_status(statuses.get(listing["id"], {}))
    _attach_walk_data(listing["id"], out)
    # Live join, not a stored column -- computed here (not just in
    # get_listing) so PATCH's response (e.g. editing council_tax_band)
    # reflects the new estimate immediately too, issue #60.
    out["council_tax_monthly_est"] = counciltax_store.monthly_estimate(
        listing.get("admin_district_gss"), listing.get("council_tax_band")
    )
    return out


def _serialize_many_with_pipeline_status(listings: list[dict]) -> list[dict]:
    statuses = queue.latest_job_statuses_for_listings([l["id"] for l in listings])
    rules = standards_store.list_rules()
    result = []
    for listing in listings:
        out = serialize_listing(listing)
        out["pipeline_status"] = derive_pipeline_status(statuses.get(listing["id"], {}))
        # Just a boolean here, not the full violation list the single-listing
        # GET returns -- the list view only needs a red-dot indicator, so
        # there's no reason to build per-field messages for every listing on
        # this hot path.
        out["has_warning"] = bool(evaluate_listing(listing, rules))
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
    out = _serialize_with_pipeline_status(store.get_listing(property_id))
    out["already_tracked"] = not inserted
    return out


@router.get("")
def list_listings(user_status: str | None = None):
    return _serialize_many_with_pipeline_status(store.list_listings(user_status))


@router.get("/{listing_id}")
def get_listing(listing_id: int):
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    out = _serialize_with_pipeline_status(listing)
    # Reads the already-guarded walk_duration_seconds values _attach_walk_data
    # attached above (via lookup_walk's stale-row check), not a fresh
    # get_walk_distances() call -- reading the raw table directly here would
    # bypass that guard and risk a min computed from a station no longer
    # among the listing's current nearest stations after a Rightmove reorder.
    nearest = out.get("nearest_stations_raw") or []
    durations = [e["walk_duration_seconds"] for e in nearest if e.get("walk_duration_seconds") is not None]
    listing["min_walk_minutes"] = round(min(durations) / 60) if durations else None
    out["standards_violations"] = evaluate_listing(listing, standards_store.list_rules())
    return out


@router.post("/{listing_id}/refresh", status_code=202)
def refresh_listing(listing_id: int, skip_llm: bool = False):
    """skip_llm=true re-scrapes and re-downloads media as normal but stops
    the auto-chain from enqueueing text_extract/floor_area_vision/epc_vision
    (see handlers.py's skip_llm_chain check) -- used by
    scripts/backfill-rightmove.sh --skip-llm for a bulk re-scrape (e.g. after
    a rightmove_extract.py field-mapping change) without triggering real,
    billed claude -p calls for every listing."""
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    # Without this guard, N rapid clicks on refresh enqueue N extraction
    # jobs for the same listing (each producing its own snapshot row and
    # media_download job) instead of just riding the one already in flight.
    # Known edge case: if a rightmove_extract job is already pending from an
    # earlier call, this guard skips enqueueing entirely -- a later call with
    # a different skip_llm value silently rides the earlier job's value
    # instead of erroring. Not worth complicating this guard for a
    # single-user tool where refresh calls aren't fired concurrently in
    # practice (backfill-rightmove.sh issues them sequentially).
    if not queue.has_pending_job(listing_id, "rightmove_extract"):
        store.set_extraction_status(listing_id, "queued")
        queue.enqueue_job(listing_id, "rightmove_extract", "http", skip_llm_chain=skip_llm)
    return _serialize_with_pipeline_status(store.get_listing(listing_id))


@router.post("/{listing_id}/walk-refresh")
def refresh_walk_distances(listing_id: int):
    """Recomputes station_walk_distances for this listing directly from
    already-stored latitude/longitude/nearest_stations_raw -- no Rightmove
    re-scrape, unlike /refresh. Same "recompute from what's already stored,
    the underlying source data hasn't changed" precedent as /llm-refresh for
    the llm lane; meant for backfilling after a walk-distance-computation
    change (see scripts/tfl-walk-backfill.sh, issue #40 PR2's schema/mode-
    mapping rewrite) without re-fetching Rightmove data that hasn't changed.

    Synchronous, not queued through the job table -- unlike /refresh and
    /llm-refresh, this is just a couple of TfL calls per station (no HTML
    fetch/parse, no claude -p call), fast enough that the job-queue's async
    tracking would be unnecessary overhead for a single-user tool. TfL's own
    rate limit is respected regardless -- tfl_client.py's throttle is
    module-level, not tied to how this function gets called.

    Skips computing (rather than raising) while a rightmove_extract job is
    pending for this listing -- same has_pending_job guard /refresh uses,
    for the same reason: a genuinely in-flight scrape's own
    compute_station_walk_distances call is about to write fresh rows keyed
    against the *new* nearest_stations_raw it just fetched. Racing ahead
    here against the *old* (pre-scrape) nearest_stations_raw and writing
    second would silently clobber the job's correct rows with stale ones --
    a real risk for scripts/tfl-walk-backfill.sh, which loops every
    listing and could overlap a concurrent scrape/bulk backfill-rightmove.sh
    run on the same listing."""
    listing = store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    if not queue.has_pending_job(listing_id, "rightmove_extract"):
        serialized = serialize_listing(listing)
        nearest_stations_raw = serialized.get("nearest_stations_raw") or []
        compute_station_walk_distances(
            listing_id, serialized.get("latitude"), serialized.get("longitude"), nearest_stations_raw
        )
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
        # postcode is EDITABLE_FIELDS (sticky once hand-edited) -- resolve
        # the council for it immediately rather than waiting for the next
        # scrape (handlers.py's own resolution already resolves against the
        # stored/sticky postcode once one exists, see its docstring, but
        # that only runs on a scrape, which may never happen again for this
        # listing). Written via apply_extracted_fields(from_scrape=False),
        # NOT folded into the apply_manual_edit call above -- that would
        # mark admin_district itself sticky and stop it from ever being
        # refreshed by a later scrape, contradicting the "always overwrite
        # freely" derived-field design (issue #60).
        if "postcode" in body.fields:
            postcode = body.fields["postcode"]
            try:
                resolved = lookup_postcode(postcode) if postcode else None
            except Exception:
                resolved = None
            store.apply_extracted_fields(
                listing_id,
                {
                    "admin_district": resolved["admin_district"] if resolved else None,
                    "admin_district_gss": resolved["codes"]["admin_district"] if resolved else None,
                },
                from_scrape=False,
            )

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
