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

**2+ change journeys (train-journey-planner issue #26):** per origin, if
/api/journeys comes back with zero journeys, this module follows train-
journey-planner's own documented two-step call contract and additionally
tries /api/journeys/multi-change (its OTP-sidecar-backed 2-5 change
fallback tier) -- but only when that first response's own
sidecar_healthy flag says it's worth the extra network round-trip, since
the endpoint always degrades to an empty result rather than erroring when
the sidecar is down. A multi-change result is tagged kind="multi_change"
(a dict key train-journey-planner's own JourneyOut doesn't carry, since
that endpoint returns a bare list of MultiChangeJourneyOut with no "kind"
field) so _num_changes/_operator/_interchange_crs below can treat all
three kinds uniformly. Never a second call once *any* earlier origin has already produced a
candidate (of any kind) -- once `best` is set, a later origin's own
/api/journeys is still tried (it's free), but a slow OTP-backed
multi-change round-trip for that origin is skipped, since a 2-5 change
result from a different origin is never going to beat an
already-found candidate once _num_changes is factored into the tiebreak.
This trades a small amount of missed cross-origin optimality on the
multi-change tier for avoiding redundant slow calls, matching train-
journey-planner's own "don't call multi-change unconditionally" guidance
in spirit.

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
from app.destinations.client import TrainPlannerApiError, fetch_journeys, fetch_multi_change_journeys
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
    if journey["kind"] == "multi_change":
        return journey.get("num_changes", 0)
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
    if journey["kind"] == "multi_change":
        legs = journey.get("legs") or []
        return legs[0].get("operator") if legs else None
    return (journey.get("interchange") or {}).get("leg1", {}).get("operator")


def _interchange_crs(journey: dict) -> str | None:
    """CRS code(s) of the station(s) where a change happens -- None for a
    direct journey. For an "interchange" journey, train-journey-planner's
    /api/journeys only ever returns 0 or 1 changes (its InterchangeTripOut
    has a single `interchange: StationOut`, not a list), so this is a
    single code. For a "multi_change" journey (train-journey-planner's
    2-5 change fallback tier, issue #26 there), MultiChangeJourneyOut has
    no equivalent single field -- the change stations are every leg's own
    destination except the journey's final leg (that one's destination is
    the overall destination, not a change) -- so this returns a
    comma-joined list of CRS codes instead of a single code. The frontend's
    routeLabel formatting already handles either shape unchanged."""
    if journey["kind"] == "multi_change":
        legs = journey.get("legs") or []
        crs_codes = [c for leg in legs[:-1] if (c := (leg.get("destination") or {}).get("crs_code"))]
        return ", ".join(crs_codes) if crs_codes else None
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
        journeys = response.get("journeys") or []
        if not journeys and response.get("sidecar_healthy") and best is None:
            # Second stage of train-journey-planner's documented two-step
            # call contract -- only worth trying when the first response
            # itself says the sidecar is healthy, since the endpoint
            # otherwise just degrades to an empty result anyway. Also
            # skipped once an earlier origin has already found a
            # direct/interchange result: a multi-change (2-5 change)
            # journey from a different origin is never going to be
            # preferred over an already-found 0/1-change journey once
            # _num_changes is factored into the tiebreak below, so paying
            # for the slow OTP-backed round-trip here would be pure waste.
            try:
                multi_response = fetch_multi_change_journeys(
                    origin["crs"], destination["crs"], target.date(), target.time()
                )
            except TrainPlannerApiError:
                multi_response = {}
            journeys = [dict(j, kind="multi_change") for j in (multi_response.get("journeys") or [])]
        candidate = _best_journey(journeys)
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
