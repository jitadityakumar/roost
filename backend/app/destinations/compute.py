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
"""
from __future__ import annotations

import datetime as dt

from app.commute.stations import resolve_crs_codes
from app.destinations import journey_store, store
from app.destinations.client import TrainPlannerApiError, fetch_journeys


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
    upcoming = [j for j in journeys if not j.get("is_past")] or journeys
    if not upcoming:
        return None
    return min(upcoming, key=lambda j: (j["duration_minutes"], _num_changes(j)))


def _operator(journey: dict) -> str | None:
    if journey["kind"] == "direct":
        return (journey.get("direct") or {}).get("operator")
    return (journey.get("interchange") or {}).get("leg1", {}).get("operator")


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
            continue

        rows.append(
            {
                "destination_id": destination["id"],
                "duration_minutes": best["duration_minutes"],
                "kind": best["kind"],
                "num_changes": _num_changes(best),
                "operator": _operator(best),
                "origin_crs": best_origin["crs"],
                "origin_name": best_origin["name"],
                "departure_time": best["departure_time"],
                "arrival_time": best["arrival_time"],
            }
        )

    journey_store.replace_journeys(listing_id, rows)
