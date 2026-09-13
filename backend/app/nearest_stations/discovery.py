"""Issue #92: discover Nearest Stations candidates via TfL's /StopPoint
lat/lon/radius search, independent of Rightmove's own nearest_stations_raw
(which only ever lists 3 stations and can omit real, closer ones) -- see the
issue's implementation plan comment for the full design.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.commute.tfl_client import (
    TflApiError,
    _DESTINATION_SEARCH_MODES,
    _strip_suffix,
    compute_walk_distance,
    search_stop_points_by_radius,
)
from app.commute.stations import _normalize_name

logger = logging.getLogger(__name__)

# Straight-line distance is always <= real walking-path distance, and TfL's
# own journey planner assumes ~80m/min walking speed -- so a 2000m
# straight-line radius is a safe upper bound that never misses a station
# reachable within a 25-min real walk (2000m / 80m-per-min = 25min), while
# still pulling in some extra candidates whose real walking path is longer
# than their straight-line distance (river/railway/park detours) -- those
# get dropped by the MAX_WALK_MINUTES filter below, not by the radius
# itself. Live-validated against real listing data, issue #92.
RADIUS_METERS = 2000
MAX_WALK_MINUTES = 25

# TfL returns a separate StopPoint per mode at the same physical station,
# each carrying the *fuller* "<Mode> Station" form in commonName (e.g.
# "Wimbledon Rail Station"/"Wimbledon Underground Station"/"Wimbledon Tram
# Stop" -- confirmed live, issue #92's validation, and matches the fuller
# suffixes tfl_client.py's own _strip_suffix already handles for the same
# reason). Reuse that function rather than a second ad hoc regex here --
# stripping just the bare mode word (no "Station") would leave these three
# un-grouped, since real TfL names don't take that shorter form.
def _group_key(name: str) -> str:
    return _normalize_name(_strip_suffix(name))


def discover_candidates(lat: float, lon: float) -> list[dict]:
    """Groups/dedups TfL's raw radius-search results by physical station
    (see _group_key), returning one row per group: {"stop_point_id"
    (canonical -- the nearest raw StopPoint id in the group), "name", "modes"
    (list, unioned across the group), "lat", "lon", "distance_meters"
    (nearest raw distance within the group)}. Never raises -- a failed radius
    search just yields []."""
    raw = search_stop_points_by_radius(lat, lon, RADIUS_METERS, _DESTINATION_SEARCH_MODES)

    groups: dict[str, list[dict]] = {}
    for sp in raw:
        groups.setdefault(_group_key(sp["name"]), []).append(sp)

    candidates = []
    for members in groups.values():
        canonical = min(members, key=lambda m: m["distance_meters"])
        modes = []
        for m in members:
            for mode in m.get("modes") or []:
                if mode not in modes:
                    modes.append(mode)
        candidates.append(
            {
                "stop_point_id": canonical["id"],
                "name": canonical["name"],
                "modes": modes,
                "lat": canonical.get("lat"),
                "lon": canonical.get("lon"),
                # TfL's radius search returns a float meters value -- round
                # to match compute_walk_distance's own convention (and the
                # INTEGER column this ends up in).
                "distance_meters": round(canonical["distance_meters"]),
            }
        )
    return candidates


def compute_nearest_stations(listing_id: int, latitude: float | None, longitude: float | None) -> None:
    """Discovers and stores nearest_station_candidates for one listing.
    Mirrors compute_station_walk_distances's never-raise contract
    (handlers.py: "This must never raise -- the rightmove_extract job has
    already succeeded by the time this runs") and its lat/lon guard.

    Unlike walk_store.replace_walk_distances, an empty/errored discovery
    result does NOT call store.replace_candidates at all -- this pipeline's
    input is a live network call, not locally-stored data, so a transient
    TfL failure must not wipe out existing good rows with an empty replace.

    Stores the full deduped candidate set, not pre-filtered to
    MAX_WALK_MINUTES -- so a future threshold change only needs a re-read
    (store.get_nearest_stations), not recomputation."""
    # Imported lazily -- store.py imports this module at top level (its
    # get_nearest_stations default arg reads MAX_WALK_MINUTES), so a
    # top-level import here would be circular.
    from app.nearest_stations import store

    if latitude is None or longitude is None:
        return

    try:
        candidates = discover_candidates(latitude, longitude)
    except Exception:
        logger.exception("nearest-stations discovery failed for listing %s", listing_id)
        return
    if not candidates:
        return

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for c in candidates:
        walk_distance_meters = None
        duration_seconds = None
        if c.get("lat") is not None and c.get("lon") is not None:
            try:
                result = compute_walk_distance(latitude, longitude, c["stop_point_id"])
                walk_distance_meters = result["distance_meters"]
                duration_seconds = result["duration_seconds"]
            except TflApiError:
                logger.info(
                    "TfL walk-duration call failed for candidate %r (listing %s) -- storing without duration",
                    c["stop_point_id"],
                    listing_id,
                )
        rows.append(
            {
                "stop_point_id": c["stop_point_id"],
                "name": c["name"],
                "modes": ",".join(c["modes"]),
                "lat": c.get("lat"),
                "lon": c.get("lon"),
                "distance_meters": c["distance_meters"],
                "walk_distance_meters": walk_distance_meters,
                "duration_seconds": duration_seconds,
                "computed_at": now,
            }
        )
    store.replace_candidates(listing_id, rows)
