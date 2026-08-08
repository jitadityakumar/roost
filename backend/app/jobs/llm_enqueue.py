"""Pre-enqueue checks for the three llm-lane job types: skip enqueueing a job
whose entire output would be discarded (every target field already sticky),
whose input doesn't exist yet (no image on disk for a vision job), or that's
already queued/running for this listing — the llm lane is strictly serial
(see worker.py), so a wasted turn here is a wasted turn for every other job
behind it, not just idle compute.
"""
from __future__ import annotations

import os

from app.config import MEDIA_DIR
from app.jobs import queue
from app.listings import store

JOB_TYPE_TARGET_FIELDS = {
    "text_extract": [
        "lease_years_remaining", "service_charge_pa", "service_charge_pm",
        "council_tax_band", "chain_free", "cash_only",
    ],
    "floor_area_vision": ["floor_area_sqft"],
    "epc_vision": ["epc_current", "epc_potential"],
}


def should_enqueue(listing_id: int, job_type: str) -> bool:
    """False if a job of this type is already queued/running for this
    listing, or if every field job_type would populate is already sticky."""
    if queue.has_pending_job(listing_id, job_type):
        return False
    return not store.target_fields_all_sticky(listing_id, JOB_TYPE_TARGET_FIELDS[job_type])


def first_media_file(listing_id: int, category: str) -> str | None:
    """Absolute path to the first (sorted) file in
    MEDIA_DIR/<listing_id>/<category>/, or None if the directory is missing
    or empty. Used both as a pre-enqueue guard for vision jobs (no image, no
    point enqueueing) and by the vision handlers to resolve the same path at
    run time. category must be one of media.py's ALLOWED_CATEGORIES
    ('floorplans', 'epc') — this function doesn't validate that, callers only
    ever pass a literal.

    Picks the first file alphabetically (Rightmove's own numbering, e.g.
    01.jpeg, 02.jpeg) when a listing has more than one floorplan or EPC
    image — a listing with two floorplans only gets the first one read. Known
    limitation, not a bug; an easy future improvement if it turns out to
    matter is to try each file until one parses.
    """
    d = os.path.join(MEDIA_DIR, str(listing_id), category)
    if not os.path.isdir(d):
        return None
    files = sorted(os.listdir(d))
    return os.path.join(d, files[0]) if files else None
