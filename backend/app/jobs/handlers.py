"""Job handlers, dispatched by job_type from the worker pool. Each handler
takes the full job row (dict) and either returns normally (job marked done)
or raises (job marked failed / requeued, see queue.fail_job).

'text_extract', 'floor_area_vision', 'epc_vision' (Phase 3, the llm lane)
read from `claude -p` via llm_client.run_claude_prompt — imported by name
(not as `llm_client.run_claude_prompt` at call sites) so tests can
monkeypatch `handlers.run_claude_prompt` directly, matching how the
Rightmove functions below are imported and mocked.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.commute import walk_store
from app.commute.tfl_client import TflApiError, compute_walk_distance, resolve_stop_point
from app.config import MEDIA_DIR
from app.crime.client import lookup_postcode
from app.destinations.compute import compute_for_listing
from app.jobs import llm_enqueue, llm_prompts, queue
from app.jobs.llm_client import JOB_TYPE_MODELS, TEXT_EXTRACT_TIMEOUT_S, VISION_TIMEOUT_S
from app.jobs.llm_client import parse_structured_output, run_claude_prompt
from app.jobs.llm_client import as_bool, as_council_tax_band, as_float, as_int, epc_rating_from_score
from app.jobs.rightmove_extract import (
    download_media,
    extract_added_on,
    extract_listing,
    fetch_broadband_summary,
    fetch_html,
    resolve_page_model,
    summarize_broadband,
)
from app.listings import normalize, store

logger = logging.getLogger(__name__)

# Rightmove's nearest_stations_raw `types` -> TfL's /StopPoint/Search `modes`
# query param. Pinned against the actual distinct `types` values observed
# across Roost's real listings (issue #40 PR2) -- NOT the plan's original
# 5-entry guess, which had DLR as "LIGHT_RAILWAY" (right) but "TRAM" as
# "TRAMLINK" (wrong; Rightmove sends "TRAM"). ELIZABETH_LINE has never been
# observed live but the frontend (NearestStations.jsx) already has a badge
# for it, so it's mapped defensively rather than left to silently no-op.
_TFL_MODE_BY_TYPE = {
    "NATIONAL_TRAIN": "national-rail",
    "LONDON_UNDERGROUND": "tube",
    "LONDON_OVERGROUND": "overground",
    "LIGHT_RAILWAY": "dlr",
    "TRAM": "tram",
    "ELIZABETH_LINE": "elizabeth-line",
}

# Widens the /StopPoint/Search modes query beyond the single canonical mode
# above, for Rightmove types where that's been observed to miss real
# stations -- see resolve_stop_point's docstring for why this is an explicit
# per-type allowlist rather than "search everything, drop bus stops" (that
# approach mis-resolved Putney Station to Putney Pier in validation).
# NATIONAL_TRAIN: TfL's own StopPoint data classifies some Rightmove-tagged
# national-rail stations (e.g. Chadwell Heath, Goodmayes) as elizabeth-line
# only.
_TFL_SEARCH_MODES_BY_TYPE = {
    "NATIONAL_TRAIN": "national-rail,elizabeth-line",
}


def _tfl_mode_for_entry(entry: dict) -> str | None:
    return _tfl_lookup_for_entry(entry)[0]


def _tfl_search_modes_for_entry(entry: dict) -> str | None:
    return _tfl_lookup_for_entry(entry)[1]


def _tfl_lookup_for_entry(entry: dict) -> tuple[str | None, str | None]:
    """(mode, search_modes) for the first Rightmove `types` entry with a TfL
    mapping -- a single scan shared by _tfl_mode_for_entry and
    _tfl_search_modes_for_entry, which both look at the same matched type."""
    for t in entry.get("types") or []:
        mode = _TFL_MODE_BY_TYPE.get(t)
        if mode:
            return mode, _TFL_SEARCH_MODES_BY_TYPE.get(t)
    return None, None


def _distance_miles_for_entry(entry: dict) -> float | None:
    """Rightmove's `distance` defaults to miles (NearestStations.jsx
    defaults `unit` the same way) but isn't guaranteed to be -- gap-scoring
    resolve_stop_point against a non-mile value would silently mis-rank
    candidates, so fall back to None (plain closest-lat/lon) if `unit` is
    ever anything else."""
    distance = entry.get("distance")
    if distance is None:
        return None
    unit = (entry.get("unit") or "mi").lower()
    if unit not in ("mi", "miles"):
        return None
    return distance


def handle_rightmove_extract(job: dict) -> None:
    listing_id = job["listing_id"]
    listing = store.get_listing(listing_id)
    if listing is None:
        raise RuntimeError(f"no listing row for id {listing_id}")

    store.set_extraction_status(listing_id, "running")

    try:
        html = fetch_html(listing["url"])
        root = resolve_page_model(html)
        prop = root["propertyData"]
    except Exception as e:
        store.set_extraction_status(listing_id, "failed", str(e))
        raise RuntimeError(f"extraction failed for listing {listing_id}: {e}") from e

    extracted = extract_listing(prop, listing_added_on=extract_added_on(root))

    postcode = None
    if extracted.get("postcode_outcode"):
        postcode = f"{extracted['postcode_outcode']} {extracted.get('postcode_incode') or ''}".strip()

    fields = {
        "price_gbp": normalize.parse_price_gbp(extracted.get("price")),
        "address": extracted.get("address"),
        "postcode": postcode,
        "property_type": extracted.get("property_type"),
        "bedrooms": extracted.get("bedrooms"),
        "bathrooms": extracted.get("bathrooms"),
        "tenure": extracted.get("tenure"),
        "description": extracted.get("description"),
        "key_features": json.dumps(extracted.get("key_features") or []),
        "nearest_stations_raw": json.dumps(extracted.get("nearest_stations") or []),
        "agent_branch": extracted.get("agent_branch"),
        "agent_address": extracted.get("agent_address"),
        "rightmove_status": json.dumps(extracted.get("status")) if extracted.get("status") else None,
        "listing_added_on": normalize.parse_yyyymmdd_date(extracted.get("listing_added_on")),
        "rightmove_fetched_at": datetime.now(timezone.utc).isoformat(),
        "latitude": extracted.get("latitude"),
        "longitude": extracted.get("longitude"),
        "pin_type": extracted.get("pin_type"),
    }

    lease_years_remaining = extracted.get("lease_years_remaining")
    is_freehold_zero = (extracted.get("tenure") or "").upper() == "FREEHOLD" and lease_years_remaining == 0
    if is_freehold_zero and listing.get("lease_years_remaining_source") not in (None, "rightmove"):
        # A non-rightmove source (the LLM lane) has already populated this
        # field from a genuine lease mention in the description/key
        # features -- leave it alone. Without this guard, a later re-scrape
        # of the same still-freehold-0 listing would silently null it back
        # out on every run, since Rightmove keeps sending 0 forever for a
        # freehold property.
        pass
    elif is_freehold_zero:
        # Freehold listings shouldn't have a lease at all -- a 0 here is
        # someone filling out Rightmove's form without understanding that 0
        # and "not applicable" aren't the same thing, not a real "0 years
        # remaining" figure. Clear the source (rather than stamping
        # "rightmove") so a genuine mention in the description/key features
        # can still let the LLM lane populate it.
        fields["lease_years_remaining"] = None
        fields["lease_years_remaining_source"] = None
    elif lease_years_remaining is not None:
        fields["lease_years_remaining"] = lease_years_remaining
        fields["lease_years_remaining_source"] = "rightmove"

    living_costs = extracted.get("living_costs") or {}

    council_tax_band = living_costs.get("councilTaxBand")
    if council_tax_band and council_tax_band.strip().upper() != "TBC":
        fields["council_tax_band"] = council_tax_band
        fields["council_tax_band_source"] = "rightmove"

    annual_service_charge = living_costs.get("annualServiceCharge")
    if annual_service_charge is not None:
        fields["service_charge_pa"] = round(annual_service_charge)
        fields["service_charge_pm"] = round(annual_service_charge / 12)
        fields["service_charge_source"] = "rightmove"

    key_features = extracted.get("key_features") or []
    structured_features = extracted.get("features") or {}

    garden = normalize.detect_garden(structured_features, key_features)
    if garden is not None:
        fields["garden"] = int(garden)
        fields["garden_source"] = "rightmove"

    parking = normalize.detect_parking(structured_features, key_features)
    if parking is not None:
        fields["parking"] = parking
        fields["parking_source"] = "rightmove"

    if postcode:
        try:
            broadband_data = fetch_broadband_summary(postcode.replace(" ", ""))
            summary = summarize_broadband(broadband_data)
            fields["broadband_top_speed"] = summary.get("top_speed")
            fields["broadband_top_speed_category"] = summary.get("top_speed_category")
            fields["broadband_top_speed_provider"] = summary.get("top_speed_provider")
        except Exception:
            pass  # broadband is a nice-to-have, not worth failing the job over

        # Council resolution (issue #60), same postcode-derived, best-effort
        # shape as broadband above. Outcode-only postcodes (rare, incode
        # missing) are excluded by the `postcode` build above already being
        # None in that case.
        #
        # postcode is a sticky EDITABLE_FIELDS entry -- once hand-edited,
        # apply_extracted_fields below will keep the *stored* postcode
        # forever and silently discard this scrape's `postcode` value. If
        # we resolved against the scraped value regardless, every future
        # re-scrape would overwrite admin_district with whatever Rightmove
        # currently reports, permanently out of sync with the postcode the
        # listing actually displays. Resolve against the listing's current
        # (possibly hand-edited) postcode instead whenever it's sticky --
        # this also self-heals any listing whose postcode was hand-edited
        # before this resolution existed at all.
        old_postcode = listing.get("postcode")
        edited_fields = json.loads(listing.get("edited_fields") or "{}")
        postcode_is_sticky = "postcode" in edited_fields
        postcode_to_resolve = old_postcode if postcode_is_sticky else postcode
        try:
            resolved = lookup_postcode(postcode_to_resolve) if postcode_to_resolve else None
        except Exception:
            resolved = None  # nice-to-have, don't fail the job over it
        if resolved:
            fields["admin_district"] = resolved["admin_district"]
            fields["admin_district_gss"] = resolved["codes"]["admin_district"]
        elif not postcode_is_sticky and postcode != old_postcode:
            # Postcode changed and the new one didn't resolve -- clear the
            # stale council rather than silently keeping the old (now
            # wrong) one attached. If postcode is unchanged (or sticky --
            # in which case we're always resolving the same postcode as
            # last time), leave whatever is already stored alone (this
            # call's own network hiccup shouldn't null out an otherwise-
            # valid resolution).
            fields["admin_district"] = None
            fields["admin_district_gss"] = None

    store.apply_extracted_fields(listing_id, fields)
    store.set_extraction_status(listing_id, "done")
    store.insert_snapshot(listing_id, fields.get("price_gbp"), fields.get("rightmove_status"), prop)

    # Unconditional, same as any other Rightmove-derived field -- TfL's API
    # is free, unlike the Google Routes API this used to call, so there's no
    # cost pressure to make this opt-out-able (skip_maps/--skip-maps removed
    # entirely, see issue #40).
    compute_station_walk_distances(
        listing_id, fields.get("latitude"), fields.get("longitude"), extracted.get("nearest_stations") or []
    )

    compute_for_listing(listing_id, fields.get("latitude"), fields.get("longitude"))

    skip_llm_chain = bool(job.get("skip_llm_chain"))
    queue.enqueue_job(
        listing_id, "media_download", "http", depends_on_job_id=job["id"], skip_llm_chain=skip_llm_chain
    )
    if not skip_llm_chain and llm_enqueue.should_enqueue(listing_id, "text_extract"):
        queue.enqueue_job(listing_id, "text_extract", "llm", depends_on_job_id=job["id"])


def compute_station_walk_distances(
    listing_id: int, latitude: float | None, longitude: float | None, nearest_stations_raw: list[dict]
) -> None:
    """Real walking distance/duration (TfL Journey Planner) to every station
    Rightmove's nearest_stations_raw returns for this listing -- every mode,
    no radius cap, computed once here at scrape time and stored, never a
    live call on page load (issue #40 PR2; PR1 was national-rail/1mi only,
    via resolve_crs_codes -- this now iterates nearest_stations_raw
    directly). A missing listing lat/lon (Rightmove's location block can be
    absent), an unmapped Rightmove `types` value, an unresolvable station
    name, or a per-station TfL failure just means that station keeps no
    stored value; the frontend falls back to Rightmove's raw distance for
    it. This must never raise -- the rightmove_extract job has already
    succeeded by the time this runs.

    Rows are stored (with rightmove_name/mode/stop_point_id, even when
    resolution/computation failed and distance_meters/duration_seconds stay
    None) keyed by the entry's position in nearest_stations_raw -- see
    walk_store.py's module docstring for why index-keying needs
    rightmove_name carried alongside it.

    Public (no leading underscore) because routes/listings.py's
    POST /{listing_id}/walk-refresh also calls this directly, against
    already-stored latitude/longitude/nearest_stations_raw, to recompute
    walk distances without a Rightmove re-scrape -- e.g. backfilling after
    a walk-distance-computation change (this PR) where the underlying
    Rightmove data hasn't changed, only how it's read."""
    if latitude is None or longitude is None:
        return

    rows = []
    for index, entry in enumerate(nearest_stations_raw):
        name = entry.get("name")
        if not name:
            continue
        mode, search_modes = _tfl_lookup_for_entry(entry)
        if mode is None:
            logger.info("no TfL mode mapping for station %r, types=%r -- skipping", name, entry.get("types"))
            continue

        stop_point_id = resolve_stop_point(
            name,
            mode,
            latitude,
            longitude,
            _distance_miles_for_entry(entry),
            search_modes=search_modes,
        )
        row = {
            "station_index": index,
            "rightmove_name": name,
            "mode": mode,
            "stop_point_id": stop_point_id,
            "distance_meters": None,
            "duration_seconds": None,
        }
        if stop_point_id is not None:
            try:
                result = compute_walk_distance(latitude, longitude, stop_point_id)
                row["distance_meters"] = result["distance_meters"]
                row["duration_seconds"] = result["duration_seconds"]
            except TflApiError:
                pass
        rows.append(row)

    walk_store.replace_walk_distances(listing_id, rows)


def handle_media_download(job: dict) -> None:
    listing_id = job["listing_id"]
    raw = store.latest_snapshot_raw(listing_id)
    if raw is None:
        raise RuntimeError(f"no snapshot data to download media from for listing {listing_id}")

    # Force our own listing id as the directory name regardless of whatever
    # type Rightmove's page model happened to use for its "id" field.
    raw = dict(raw)
    raw["id"] = str(listing_id)
    download_media(raw, MEDIA_DIR)

    # Vision jobs chain off media_download, not directly off
    # rightmove_extract: they need the image files on disk, and
    # rightmove_extract → media_download is itself an http-lane job that
    # might not even be claimed yet by the time rightmove_extract finishes.
    # This still satisfies "auto-chain after the rightmove extract" — just
    # transitively, via the existing rightmove_extract → media_download edge.
    if job.get("skip_llm_chain"):
        return
    if llm_enqueue.should_enqueue(listing_id, "floor_area_vision") and llm_enqueue.first_media_file(
        listing_id, "floorplans"
    ):
        queue.enqueue_job(listing_id, "floor_area_vision", "llm", depends_on_job_id=job["id"])
    if llm_enqueue.should_enqueue(listing_id, "epc_vision") and llm_enqueue.first_media_file(listing_id, "epc"):
        queue.enqueue_job(listing_id, "epc_vision", "llm", depends_on_job_id=job["id"])


def handle_text_extract(job: dict) -> None:
    listing_id = job["listing_id"]
    listing = store.get_listing(listing_id)
    if listing is None:
        raise RuntimeError(f"no listing row for id {listing_id}")
    description = listing.get("description")
    if not description:
        return  # nothing to extract from; not an error, just a no-op completion

    key_features = json.loads(listing.get("key_features") or "[]")
    key_features_text = "\n".join(f"- {f}" for f in key_features) if key_features else "(none listed)"

    prompt = llm_prompts.TEXT_EXTRACT_PROMPT.format(description=description, key_features=key_features_text)
    raw = run_claude_prompt(
        prompt,
        JOB_TYPE_MODELS["text_extract"],
        TEXT_EXTRACT_TIMEOUT_S,
        json_schema=llm_prompts.TEXT_EXTRACT_SCHEMA,
        disallow_all_tools=True,
    )
    parsed = parse_structured_output(raw)

    # Rightmove's structured livingCosts data (see PR #5) always wins over an
    # LLM read of the free-text description for the fields both can produce
    # — skip any field already sourced 'rightmove' so this handler can never
    # regress that fix. A field not yet populated by either source has no
    # '_source' value at all, so it's untouched by this check.
    fields = {}
    if listing.get("lease_years_remaining_source") != "rightmove":
        lease_years = as_int(parsed.get("lease_years_remaining"))
        if lease_years is not None:
            fields["lease_years_remaining"] = lease_years
            fields["lease_years_remaining_source"] = "llm"

    if listing.get("service_charge_source") != "rightmove":
        service_charge = as_int(parsed.get("service_charge_pa"))
        if service_charge is not None:
            fields["service_charge_pa"] = service_charge
            fields["service_charge_pm"] = round(service_charge / 12)
            fields["service_charge_source"] = "llm"

    if listing.get("council_tax_band_source") != "rightmove":
        band = as_council_tax_band(parsed.get("council_tax_band"))
        if band is not None:
            fields["council_tax_band"] = band
            fields["council_tax_band_source"] = "llm"

    if listing.get("chain_free_source") != "rightmove":
        chain_free = as_bool(parsed.get("chain_free"))
        if chain_free is not None:
            fields["chain_free"] = int(chain_free)
            fields["chain_free_source"] = "llm"

    if listing.get("cash_only_source") != "rightmove":
        cash_only = as_bool(parsed.get("cash_only"))
        if cash_only is not None:
            fields["cash_only"] = int(cash_only)
            fields["cash_only_source"] = "llm"

    if fields:
        store.apply_extracted_fields(listing_id, fields)


def handle_floor_area_vision(job: dict) -> None:
    listing_id = job["listing_id"]
    listing = store.get_listing(listing_id)
    if listing is None:
        raise RuntimeError(f"no listing row for id {listing_id}")
    image_path = llm_enqueue.first_media_file(listing_id, "floorplans")
    if image_path is None:
        raise RuntimeError(f"no floorplan image on disk for listing {listing_id}")
    if listing.get("floor_area_sqft_source") == "rightmove":
        return  # a structured/text source already won; nothing for this job to do

    prompt = llm_prompts.FLOOR_AREA_VISION_PROMPT.format(image_path=image_path)
    raw = run_claude_prompt(
        prompt,
        JOB_TYPE_MODELS["floor_area_vision"],
        VISION_TIMEOUT_S,
        allow_read=True,
        json_schema=llm_prompts.FLOOR_AREA_VISION_SCHEMA,
    )
    parsed = parse_structured_output(raw)

    sqft = as_float(parsed.get("floor_area_sqft"))
    if sqft is None:
        sqm = as_float(parsed.get("floor_area_sqm"))
        if sqm is not None:
            sqft = normalize.sqm_to_sqft(sqm)
    if sqft is not None:
        store.apply_extracted_fields(listing_id, {"floor_area_sqft": sqft, "floor_area_sqft_source": "llm"})


def handle_epc_vision(job: dict) -> None:
    listing_id = job["listing_id"]
    listing = store.get_listing(listing_id)
    if listing is None:
        raise RuntimeError(f"no listing row for id {listing_id}")
    image_path = llm_enqueue.first_media_file(listing_id, "epc")
    if image_path is None:
        raise RuntimeError(f"no EPC image on disk for listing {listing_id}")
    if listing.get("epc_source") == "rightmove":
        return  # a structured/text source already won; nothing for this job to do

    prompt = llm_prompts.EPC_VISION_PROMPT.format(image_path=image_path)
    raw = run_claude_prompt(
        prompt,
        JOB_TYPE_MODELS["epc_vision"],
        VISION_TIMEOUT_S,
        allow_read=True,
        json_schema=llm_prompts.EPC_VISION_SCHEMA,
    )
    parsed = parse_structured_output(raw)

    fields = {}
    current = epc_rating_from_score(parsed.get("epc_current_score"))
    if current is not None:
        fields["epc_current"] = current
        fields["epc_source"] = "llm"
    potential = epc_rating_from_score(parsed.get("epc_potential_score"))
    if potential is not None:
        fields["epc_potential"] = potential
        fields["epc_source"] = "llm"
    if fields:
        store.apply_extracted_fields(listing_id, fields)


HANDLERS = {
    "rightmove_extract": handle_rightmove_extract,
    "media_download": handle_media_download,
    "text_extract": handle_text_extract,
    "floor_area_vision": handle_floor_area_vision,
    "epc_vision": handle_epc_vision,
}
