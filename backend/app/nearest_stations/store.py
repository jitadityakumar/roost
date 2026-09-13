"""Plain CRUD for nearest_station_candidates (migration 0031). Rows for a
listing are deleted and reinserted wholesale on each recompute, same
delete-then-reinsert pattern as walk_store.replace_walk_distances -- unlike
that table, no staleness guard is needed on read (stop_point_id is a stable
TfL identifier, not an index into Rightmove's reorderable
nearest_stations_raw).
"""
from __future__ import annotations

from app.commute.maps_url import maps_walking_url
from app.db.connection import get_connection
from app.nearest_stations import discovery
from app.nearest_stations.modes import modes_to_rightmove_types


def replace_candidates(listing_id: int, rows: list[dict]) -> None:
    """rows: [{"stop_point_id": str, "name": str, "modes": str (comma-
    joined), "lat": float | None, "lon": float | None,
    "distance_meters": int (straight-line), "walk_distance_meters": int |
    None (routed), "duration_seconds": int | None, "computed_at": str}]."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM nearest_station_candidates WHERE listing_id = ?", (listing_id,))
        conn.executemany(
            "INSERT INTO nearest_station_candidates "
            "(listing_id, stop_point_id, name, modes, lat, lon, distance_meters, "
            "walk_distance_meters, duration_seconds, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    listing_id,
                    r["stop_point_id"],
                    r["name"],
                    r["modes"],
                    r.get("lat"),
                    r.get("lon"),
                    r["distance_meters"],
                    r.get("walk_distance_meters"),
                    r.get("duration_seconds"),
                    r["computed_at"],
                )
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_nearest_stations(
    listing_id: int,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    max_walk_minutes: int = discovery.MAX_WALK_MINUTES,
) -> list[dict]:
    """Reads all stored candidates for a listing, drops any with no walking
    duration or over max_walk_minutes, and returns them sorted by duration
    ascending. Field names deliberately match what _attach_walk_data already
    produces for nearest_stations_raw (walk_distance_meters,
    walk_duration_seconds, walk_maps_url) so NearestStations.jsx needs
    minimal change -- plus "straight_line_meters" (this row's own
    distance_meters, from the radius search) kept under a distinct name so
    it can't be confused with walk_distance_meters, and "types" (modes
    translated to Rightmove-type keys, see nearest_stations.modes.
    modes_to_rightmove_types) so the existing badge/logo lookups (both keyed
    by Rightmove type) don't need to change."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT stop_point_id, name, modes, lat, lon, distance_meters, "
            "walk_distance_meters, duration_seconds "
            "FROM nearest_station_candidates WHERE listing_id = ?",
            (listing_id,),
        ).fetchall()
    finally:
        conn.close()

    max_seconds = max_walk_minutes * 60
    result = []
    for r in rows:
        duration = r["duration_seconds"]
        if duration is None or duration > max_seconds:
            continue
        walk_maps_url = None
        if (
            r["lat"] is not None
            and r["lon"] is not None
            and origin_lat is not None
            and origin_lon is not None
        ):
            walk_maps_url = maps_walking_url(origin_lat, origin_lon, r["lat"], r["lon"])
        result.append(
            {
                "name": r["name"],
                "types": modes_to_rightmove_types((r["modes"] or "").split(",")),
                "straight_line_meters": r["distance_meters"],
                "walk_distance_meters": r["walk_distance_meters"],
                "walk_duration_seconds": duration,
                "walk_maps_url": walk_maps_url,
            }
        )
    result.sort(key=lambda s: s["walk_duration_seconds"])
    return result
