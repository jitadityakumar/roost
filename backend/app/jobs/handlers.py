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

from app.config import MEDIA_DIR
from app.jobs import llm_enqueue, llm_prompts, queue
from app.jobs.llm_client import JOB_TYPE_MODELS, TEXT_EXTRACT_TIMEOUT_S, VISION_TIMEOUT_S
from app.jobs.llm_client import extract_json_block, run_claude_prompt
from app.jobs.llm_client import as_bool, as_council_tax_band, as_epc_rating, as_float, as_int
from app.jobs.rightmove_extract import (
    download_media,
    extract_listing,
    fetch_broadband_summary,
    fetch_html,
    resolve_page_model,
    summarize_broadband,
)
from app.listings import normalize, store


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

    extracted = extract_listing(prop)

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
    }

    if extracted.get("lease_years_remaining") is not None:
        fields["lease_years_remaining"] = extracted["lease_years_remaining"]
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

    store.apply_extracted_fields(listing_id, fields)
    store.set_extraction_status(listing_id, "done")
    store.insert_snapshot(listing_id, fields.get("price_gbp"), fields.get("rightmove_status"), prop)

    queue.enqueue_job(listing_id, "media_download", "http", depends_on_job_id=job["id"])
    if llm_enqueue.should_enqueue(listing_id, "text_extract"):
        queue.enqueue_job(listing_id, "text_extract", "llm", depends_on_job_id=job["id"])


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

    prompt = llm_prompts.TEXT_EXTRACT_PROMPT.format(description=description)
    raw = run_claude_prompt(prompt, JOB_TYPE_MODELS["text_extract"], TEXT_EXTRACT_TIMEOUT_S)
    parsed = extract_json_block(raw)

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
        prompt, JOB_TYPE_MODELS["floor_area_vision"], VISION_TIMEOUT_S, allow_read=True
    )
    parsed = extract_json_block(raw)

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
    raw = run_claude_prompt(prompt, JOB_TYPE_MODELS["epc_vision"], VISION_TIMEOUT_S, allow_read=True)
    parsed = extract_json_block(raw)

    fields = {}
    current = as_epc_rating(parsed.get("epc_current"))
    if current is not None:
        fields["epc_current"] = current
        fields["epc_source"] = "llm"
    potential = as_epc_rating(parsed.get("epc_potential"))
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
