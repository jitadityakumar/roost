"""Derives a single user-facing pipeline stage for a listing from the
per-job-type statuses in the `jobs` table (see queue.py for the schema).

This is deliberately separate from `listings.extraction_status`, which only
ever reflects `rightmove_extract` (see handlers.py) and says nothing about
`media_download` or the llm-lane jobs — a listing can be fully viewable
(rightmove data present) while media/LLM enrichment is still in flight, and
the UI wants a single badge that reflects the whole pipeline, not just the
first stage of it.
"""
from __future__ import annotations

_LLM_STAGE_JOB_TYPES = ("text_extract", "floor_area_vision", "epc_vision")

_IN_FLIGHT = ("queued", "running")


def derive_pipeline_status(latest_by_type: dict[str, str]) -> str | None:
    """`latest_by_type` maps job_type -> status for that job_type's most
    recent row (a listing accumulates one row per job_type per
    Refresh/backfill, so "latest" is the only one that matters here — see
    queue.latest_job_statuses_for_listings). A job_type absent from the dict
    means it was never enqueued for this listing (e.g. no floorplan image,
    so floor_area_vision was intentionally skipped) and is not treated as an
    error or an in-progress stage.

    Returns one of 'queued', 'fetching', 'processing', 'failed', or None
    (nothing worth showing — either every job is done, or no jobs exist yet
    for this listing).

    Deliberately checks stages in pipeline order (rightmove_extract ->
    media_download -> llm lane) rather than scanning for any 'failed' row
    up front. A Refresh only re-enqueues rightmove_extract immediately;
    media_download and the llm-lane jobs only get a fresh row once that new
    rightmove_extract job actually completes (see handlers.py). Scanning
    for 'failed' anywhere would keep reporting a stale failure from
    *before* the Refresh (e.g. a media_download that failed last time)
    while a brand-new rightmove_extract is happily queued/running —
    checking stage-by-stage means a failure only counts once its stage is
    actually the current one, not superseded by an earlier stage starting
    over.
    """
    if not latest_by_type:
        return None

    rightmove_status = latest_by_type.get("rightmove_extract")
    if rightmove_status in (None, "queued"):
        return "queued"
    if rightmove_status == "failed":
        return "failed"
    if rightmove_status == "running":
        return "fetching"

    media_status = latest_by_type.get("media_download")
    if media_status == "failed":
        return "failed"
    if media_status in _IN_FLIGHT:
        return "fetching"

    llm_statuses = [latest_by_type.get(job_type) for job_type in _LLM_STAGE_JOB_TYPES]
    if any(status == "failed" for status in llm_statuses):
        return "failed"
    if any(status in _IN_FLIGHT for status in llm_statuses):
        return "processing"

    return None
