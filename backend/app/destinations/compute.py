"""Per-listing frequent-destination journey computation -- see GitHub issue
#28, replaced onto TfL's Unified Journey Planner API by issue #47 (full
replacement of train-journey-planner, not a fallback tier).

For every enabled frequent destination, queries
app.commute.tfl_client.find_frequent_destination_journey once with the
listing's own raw latitude/longitude as the origin -- TfL's `from` accepts a
lat/lon pair directly, so unlike the old GTFS planner there's no
per-candidate-origin-station loop and no CRS resolution step at all. This is
what closes the Tube/DLR/Overground/tram-only gap the old CRS-only
`resolve_crs_codes` candidate set structurally couldn't reach (Southfields,
Pudding Mill Lane -- see issue #47's spike). A destination whose
`tfl_identifier` isn't set yet (nullable at the DB level, see migration
0019), or whose listing has no resolved lat/lon, or whose TfL query finds no
journey in the scan window, simply gets no stored row -- the frontend
renders that as "no journey found", same degrade-gracefully behavior as
before.

**Backfill on destination create/edit (GitHub issue #36)**: unlike the
walking-distance Google Maps calls, TfL's API is free, so there's no cost
reason to make the admin run a separate backfill step after adding or
editing a destination. routes/destinations.py fires compute_for_destination()
as a background task right after the response is sent, looping every
existing listing and recomputing just that one destination -- see that
function's docstring. Progress is tracked in app.destinations.backfill_status
(in-memory, not persisted) so the admin page can poll and show a progress
bar instead of blocking on the whole backfill.

**Home-vs-listing comparison**: compute_for_destination also computes (via
compute_home_journey) a single journey from the user's own home lat/lon
(ROOST_HOME_LAT/ROOST_HOME_LON, app/config.py) to the destination, stored in
home_journeys keyed by destination_id alone -- unlike destination_journeys,
there's no per-listing loop here since home is one fixed origin. There's no
separate "did the schedule change" invalidation path for this -- it doesn't
need one, since it's recomputed via this same function on every call,
including a PATCH edit to day_of_week/time/tfl_identifier (any non-empty
PATCH already re-triggers compute_for_destination, see routes/
destinations.py). In practice the admin UI never exposes editing those
fields (delete + recreate only), so this only ever runs once per
destination's lifetime today -- but that's a UI choice, not something this
function depends on for correctness.
"""
from __future__ import annotations

import datetime as dt
import logging
import time

from app import config
from app.commute.tfl_client import find_frequent_destination_journey
from app.destinations import backfill_status, journey_store, store
from app.listings import store as listings_store
from app.listings.serialize import serialize_listing

logger = logging.getLogger(__name__)


def next_occurrence(day_of_week: int, time_str: str, now: dt.datetime | None = None) -> dt.datetime:
    """Next date/time (today counts if it's still upcoming) matching the
    destination's target weekday (0=Monday..6=Sunday, date.weekday()
    convention) and HH:MM time, as Europe/London wall-clock -- same
    convention the TfL query itself uses for its date/time params. Always
    lands within TfL's supported ~7-day-past/90-day-future window (confirmed
    live, issue #47 spike)."""
    now = now or dt.datetime.now()
    target_time = dt.datetime.strptime(time_str, "%H:%M").time()
    days_ahead = (day_of_week - now.weekday()) % 7
    candidate_date = now.date() + dt.timedelta(days=days_ahead)
    if days_ahead == 0 and target_time <= now.time():
        candidate_date += dt.timedelta(days=7)
    return dt.datetime.combine(candidate_date, target_time)


def _journey_row(
    destination: dict, latitude: float | None, longitude: float | None, retry_on_empty: bool = False
) -> tuple[dict | None, dict | None]:
    """Best journey to `destination` from (latitude, longitude), as a
    destination_journeys row dict -- or None if the destination has no
    tfl_identifier yet, the listing has no resolved lat/lon, or TfL found no
    journey in the scan window. Must be an explicit guard, not implicit --
    every destination is tfl_identifier IS NULL immediately after migration
    0019 lands, until it's re-picked through the admin form; calling TfL
    with to=None would be a real bug, not just a "no route" degrade.

    `retry_on_empty` (issue #54) is passed straight through to
    find_frequent_destination_journey -- see its docstring. Only
    compute_for_destination (backfills) opts in; compute_for_listing (scrape
    pipeline + the interactive recompute button) doesn't.

    Returns `(row, pool)` (issue #59) -- `pool` is the raw candidate journey
    pool behind the pick (`{"query_params", "candidate_pool"}`), or None
    when there's no row to attach one to."""
    if latitude is None or longitude is None:
        return None, None
    tfl_identifier = destination.get("tfl_identifier")
    if not tfl_identifier:
        return None, None

    target = next_occurrence(destination["day_of_week"], destination["time"])
    pool_holder: dict = {}
    journey = find_frequent_destination_journey(
        latitude,
        longitude,
        tfl_identifier,
        target.date(),
        target.time(),
        retry_on_empty=retry_on_empty,
        pool_out=pool_holder,
    )
    if journey is None:
        return None, None

    # journey's keys (duration_minutes, kind, num_changes, operator,
    # origin_crs, origin_name, arrival_name, interchange_crs,
    # departure_time, arrival_time) already match journey_store's row shape
    # 1:1 -- see tfl_client.py::_extract_journey.
    return {"destination_id": destination["id"], **journey}, (pool_holder or None)


def compute_home_journey(destination: dict) -> None:
    """Computes and stores this destination's home_journeys row from
    ROOST_HOME_LAT/ROOST_HOME_LON (app.config) -- the fixed origin for the
    home-vs-listing duration comparison (routes/destination_journeys.py).
    Clears any stored row instead if either env var is unset (no home
    configured -- the expected state on a fresh/public deployment, see
    config.py) or the destination is disabled, matching
    compute_for_listing's "disabled destinations aren't stored" behavior.
    Computed once per call, not once per listing -- home is a single fixed
    origin shared across every listing, unlike destination_journeys."""
    if not destination["enabled"] or config.HOME_LAT is None or config.HOME_LON is None:
        journey_store.delete_home_journey(destination["id"])
        return
    row, _pool = _journey_row(destination, config.HOME_LAT, config.HOME_LON, retry_on_empty=True)
    journey_store.set_home_journey(destination["id"], row)


def compute_for_listing(listing_id: int, latitude: float | None, longitude: float | None) -> None:
    """Must never raise -- called from handle_rightmove_extract after the
    scrape job has already succeeded, and from the manual-refresh route
    where a partial result (some destinations resolved, some not) is still
    useful. A listing with no resolved lat/lon (real case -- handlers.py
    already treats this as possible for the walk-distance computation)
    clears any stored journeys and contributes nothing, same as today's "no
    usable origin" case -- there's no station-name-matching fallback the way
    the old CRS-based candidate set had."""
    if latitude is None or longitude is None:
        journey_store.replace_journeys(listing_id, [])
        return

    entries = []
    for destination in store.list_destinations():
        if not destination["enabled"]:
            continue
        row, pool = _journey_row(destination, latitude, longitude)
        if row is not None:
            entries.append((row, pool))

    journey_store.replace_journeys(listing_id, entries)


def compute_for_destination(destination_id: int) -> None:
    """Backfills a single destination's journeys across every existing
    listing -- called as a background task from routes/destinations.py
    right after a destination is created or its day/time/tfl_identifier/
    enabled state changes, so existing listings pick it up without the
    admin request blocking on the whole backfill (issue #36) or needing a
    separate backfill script for a create/edit. (Re-triggering every
    existing destination at once -- e.g. after a migration -- can reuse this
    same path via a no-op PATCH per destination; no dedicated backfill
    script exists for issue #47's migration since both destination tables
    were empty when it landed.) Safe to call often: TfL's API is free,
    unlike the Google Maps walking-distance calls that a bulk backfill has
    to guard against with --skip-maps. A disabled destination's stored rows
    are cleared instead of recomputed, matching compute_for_listing's
    "disabled destinations aren't stored" behavior.

    Reports progress via backfill_status, keyed by destination_id --
    routes/destinations.py has already called backfill_status.start()
    synchronously (before this function ever starts running, on a
    background thread) so that a client polling the status route
    immediately after the create/edit request returns is guaranteed to see
    'running', never a stale 'done' left over from a previous run of this
    same destination_id."""
    destination = next((d for d in store.list_destinations() if d["id"] == destination_id), None)
    if destination is None:
        backfill_status.finish(destination_id, "done")
        return

    listings = listings_store.list_listings()
    started = time.monotonic()
    try:
        compute_home_journey(destination)
        for listing in listings:
            listing_id = listing["id"]
            if not destination["enabled"]:
                journey_store.delete_for_destination(listing_id, destination_id)
            else:
                serialized = serialize_listing(listing)
                row, pool = _journey_row(
                    destination, serialized.get("latitude"), serialized.get("longitude"), retry_on_empty=True
                )
                journey_store.replace_single(listing_id, destination_id, row, pool)
            backfill_status.increment(destination_id)
    except Exception:
        backfill_status.finish(destination_id, "failed")
        raise

    backfill_status.finish(destination_id, "done")
    elapsed = time.monotonic() - started
    logger.info(
        "compute_for_destination(%s): backfilled %d listings in %.1fs",
        destination_id,
        len(listings),
        elapsed,
    )
