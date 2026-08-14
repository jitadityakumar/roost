"""Per-listing frequent-destination journey computation -- see GitHub issue
#28. Computed once, at scrape time (app/jobs/handlers.py) or on manual
recompute (routes/listings.py), never a live call on page load, same
precedent as app/commute/walking.py's station walk distances.

For every enabled frequent destination, queries train-journey-planner's
/api/journeys from every station within the listing's existing
resolve_crs_codes() radius to the destination's CRS, for the destination's
next occurrence of its target day-of-week/time, and keeps the best
(fastest, then fewest changes) result found across all candidate origins.
A destination with no route found from any origin -- or whose CRS code is
unresolvable, or a request that errors -- simply gets no stored row; the
frontend renders that as "no route found", which issue #28 explicitly
scopes as a flag for #25's Google Maps fallback to eventually act on, not
something this module raises or retries over.

**Backfill on destination create/edit**: unlike the walking-distance Google
Maps calls, train-journey-planner is local/free, so there's no cost reason
to make the admin run a separate backfill step after adding or editing a
destination. routes/destinations.py calls compute_for_destination()
synchronously in the same request, looping every existing listing and
recomputing just that one destination -- see that function's docstring.
"""
from __future__ import annotations

import datetime as dt
import logging
import time

from app.commute.stations import resolve_crs_codes
from app.destinations import journey_store, store
from app.destinations.client import TrainPlannerApiError, fetch_journeys
from app.listings import store as listings_store
from app.listings.serialize import serialize_listing

logger = logging.getLogger(__name__)


def next_occurrence(day_of_week: int, time_str: str, now: dt.datetime | None = None) -> dt.datetime:
    """Next date/time (today counts if it's still upcoming) matching the
    destination's target weekday (0=Monday..6=Sunday, date.weekday()
    convention) and HH:MM time, as Europe/London wall-clock -- same
    convention train-journey-planner itself uses for date/time params."""
    now = now or dt.datetime.now()
    target_time = dt.datetime.strptime(time_str, "%H:%M").time()
    days_ahead = (day_of_week - now.weekday()) % 7
    candidate_date = now.date() + dt.timedelta(days=days_ahead)
    if days_ahead == 0 and target_time <= now.time():
        candidate_date += dt.timedelta(days=7)
    return dt.datetime.combine(candidate_date, target_time)


def _num_changes(journey: dict) -> int:
    return 0 if journey["kind"] == "direct" else 1


def _best_journey(journeys: list[dict]) -> dict | None:
    upcoming = [j for j in journeys if not j.get("is_past")]
    if not upcoming:
        # Every returned journey has already departed -- since the query is
        # always for a future next_occurrence(), this should be rare (only
        # near the boundary of "today, right around the target time"). Treat
        # it the same as "no route found" rather than storing an
        # already-departed train as the answer.
        return None
    return min(upcoming, key=lambda j: (j["duration_minutes"], _num_changes(j)))


def _operator(journey: dict) -> str | None:
    if journey["kind"] == "direct":
        return (journey.get("direct") or {}).get("operator")
    return (journey.get("interchange") or {}).get("leg1", {}).get("operator")


def _interchange_crs(journey: dict) -> str | None:
    """CRS code of the station where the change happens, for an
    "interchange" journey -- None for a direct journey. train-journey-
    planner's /api/journeys only ever returns 0 or 1 changes (its
    InterchangeTripOut has a single `interchange: StationOut`, not a list),
    so this is always a single code today."""
    if journey["kind"] != "interchange":
        return None
    return (journey.get("interchange") or {}).get("interchange", {}).get("crs_code")


def _best_across_origins(destination: dict, origins: list[dict]) -> dict | None:
    """Best (fastest, fewest-changes tiebreak) journey to `destination` found
    across every candidate origin station, as a destination_journeys row
    dict -- or None if no origin returned a route. A per-origin
    TrainPlannerApiError (network failure, unresolvable CRS) is skipped,
    not raised; the caller decides what "no result at all" means for
    storage."""
    target = next_occurrence(destination["day_of_week"], destination["time"])

    best = None
    best_origin = None
    for origin in origins:
        try:
            response = fetch_journeys(origin["crs"], destination["crs"], target.date(), target.time())
        except TrainPlannerApiError:
            continue
        candidate = _best_journey(response.get("journeys") or [])
        if candidate is None:
            continue
        if best is None or (candidate["duration_minutes"], _num_changes(candidate)) < (
            best["duration_minutes"],
            _num_changes(best),
        ):
            best = candidate
            best_origin = origin

    if best is None:
        return None
    return {
        "destination_id": destination["id"],
        "duration_minutes": best["duration_minutes"],
        "kind": best["kind"],
        "num_changes": _num_changes(best),
        "operator": _operator(best),
        "origin_crs": best_origin["crs"],
        "origin_name": best_origin["name"],
        "interchange_crs": _interchange_crs(best),
        "departure_time": best["departure_time"],
        "arrival_time": best["arrival_time"],
    }


def compute_for_listing(listing_id: int, nearest_stations_raw: list[dict]) -> None:
    """Must never raise -- called from handle_rightmove_extract after the
    scrape job has already succeeded, and from the manual-refresh route
    where a partial result (some destinations resolved, some not) is still
    useful. A missing ROOST_TRAIN_PLANNER_BASE or an unreachable service
    means every destination simply gets no stored row, same degrade-
    gracefully behavior as a missing GOOGLE_MAPS_API_KEY."""
    origins = resolve_crs_codes(nearest_stations_raw)
    if not origins:
        journey_store.replace_journeys(listing_id, [])
        return

    rows = []
    for destination in store.list_destinations():
        if not destination["enabled"]:
            continue
        row = _best_across_origins(destination, origins)
        if row is not None:
            rows.append(row)

    journey_store.replace_journeys(listing_id, rows)


def compute_for_destination(destination_id: int) -> None:
    """Backfills a single destination's journeys across every existing
    listing -- called synchronously from routes/destinations.py right after
    a destination is created or its day/time/CRS/enabled state changes, so
    existing listings pick it up immediately without a separate backfill
    script or a manual per-listing refresh click. Safe to call often:
    train-journey-planner is local/free, unlike the Google Maps walking-
    distance calls that a bulk backfill has to guard against with
    --skip-maps. A disabled destination's stored rows are cleared instead
    of recomputed, matching compute_for_listing's "disabled destinations
    aren't stored" behavior."""
    destination = next((d for d in store.list_destinations() if d["id"] == destination_id), None)
    if destination is None:
        return

    started = time.monotonic()
    listings = listings_store.list_listings()
    for listing in listings:
        listing_id = listing["id"]
        if not destination["enabled"]:
            journey_store.delete_for_destination(listing_id, destination_id)
            continue
        serialized = serialize_listing(listing)
        origins = resolve_crs_codes(serialized.get("nearest_stations_raw") or [])
        row = _best_across_origins(destination, origins) if origins else None
        journey_store.replace_single(listing_id, destination_id, row)

    elapsed = time.monotonic() - started
    logger.info(
        "compute_for_destination(%s): backfilled %d listings in %.1fs",
        destination_id,
        len(listings),
        elapsed,
    )
