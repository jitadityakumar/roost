"""Job handlers, dispatched by job_type from the worker pool. Each handler
takes the full job row (dict) and either returns normally (job marked done)
or raises (job marked failed / requeued, see queue.fail_job).

Only 'rightmove_extract' and 'media_download' are implemented — Phase 1 never
enqueues 'llm' lane jobs (floor_area_vision / epc_vision / text_extract),
so no handler exists for them yet (Phase 3 work).
"""
from __future__ import annotations

import json

from app.config import MEDIA_DIR
from app.jobs import queue
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


HANDLERS = {
    "rightmove_extract": handle_rightmove_extract,
    "media_download": handle_media_download,
}
