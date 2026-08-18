"""Leg-by-leg parsing of one raw TfL journey dict from a stored
journey_scan_pools.candidate_pool entry, for the issue #59 details page.
Parsing only -- no DB access, imported by routes/journey_details.py.

`_extract_journey` in app.commute.tfl_client only extracts a single
best-leg summary (what destination_journeys stores); this module produces
the full per-leg breakdown the details page's expandable candidate list
needs, reusing the same journey-summary extraction for each candidate's
collapsed-row fields."""
from __future__ import annotations

from app.commute.tfl_client import _extract_journey, _leg_operator, _leg_point, _parse_tfl_datetime


def _parse_leg(leg: dict, next_leg: dict | None) -> dict:
    mode = (leg.get("mode") or {}).get("id")
    parsed = {
        "mode": mode,
        "operator": _leg_operator(leg),
        "departure_time": leg.get("departureTime"),
        "arrival_time": leg.get("arrivalTime"),
        "duration": leg.get("duration"),
        "from": _leg_point(leg, "departurePoint").get("commonName"),
        "to": _leg_point(leg, "arrivalPoint").get("commonName"),
    }

    if next_leg is not None:
        this_arrival = _parse_tfl_datetime(leg.get("arrivalTime"))
        next_departure = _parse_tfl_datetime(next_leg.get("departureTime"))
        if this_arrival is not None and next_departure is not None:
            gap_minutes = round((next_departure - this_arrival).total_seconds() / 60)
            if gap_minutes > 0:
                parsed["change_minutes"] = gap_minutes

    return parsed


def parse_candidate(journey: dict) -> dict:
    """One candidate_pool entry -> {"duration_minutes", "num_changes",
    "kind", "start_time", "arrival_time", "legs": [...]}. Candidates were
    already filtered to `_extract_journey(journey) is not None` before
    storage (see tfl_client.py's pool-collection code), so the summary
    extraction here is expected to succeed -- but a legitimately unparsable
    stored entry (should not happen) degrades to a legs-only shape rather
    than raising, since this route serves a details/debugging page, not a
    critical path."""
    legs = journey.get("legs") or []
    parsed_legs = [_parse_leg(leg, legs[i + 1] if i + 1 < len(legs) else None) for i, leg in enumerate(legs)]

    summary = _extract_journey(journey) or {}
    return {
        "duration_minutes": summary.get("duration_minutes"),
        "num_changes": summary.get("num_changes"),
        "kind": summary.get("kind"),
        "start_time": journey.get("startDateTime"),
        "arrival_time": journey.get("arrivalDateTime"),
        "legs": parsed_legs,
    }
