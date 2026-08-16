"""Plain CRUD for station_walk_distances (migration 0011, re-keyed by
migration 0018 -- see that migration's comment for why). Rows for a listing
are deleted and reinserted wholesale on each recompute, not upserted
individually -- see context.md's "Station walking distance" section.

Keyed by (listing_id, station_index) -- station_index is the row's position
in Rightmove's nearest_stations_raw list at compute time, not a CRS code
(tube/tram/DLR/overground stations have none). See lookup_walk() for the
safety guard this requires at read time.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection


def replace_walk_distances(listing_id: int, rows: list[dict]) -> None:
    """rows: [{"station_index": int, "rightmove_name": str,
    "mode": str | None, "stop_point_id": str | None,
    "distance_meters": int | None, "duration_seconds": int | None}]."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM station_walk_distances WHERE listing_id = ?", (listing_id,))
        conn.executemany(
            "INSERT INTO station_walk_distances "
            "(listing_id, station_index, rightmove_name, mode, stop_point_id, "
            "distance_meters, duration_seconds, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    listing_id,
                    r["station_index"],
                    r["rightmove_name"],
                    r.get("mode"),
                    r.get("stop_point_id"),
                    r["distance_meters"],
                    r["duration_seconds"],
                    now,
                )
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_walk_distances(listing_id: int) -> dict[int, dict]:
    """Returns {station_index: {"rightmove_name", "mode", "stop_point_id",
    "distance_meters", "duration_seconds"}}."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT station_index, rightmove_name, mode, stop_point_id, distance_meters, duration_seconds "
            "FROM station_walk_distances WHERE listing_id = ?",
            (listing_id,),
        ).fetchall()
        return {
            r["station_index"]: {
                "rightmove_name": r["rightmove_name"],
                "mode": r["mode"],
                "stop_point_id": r["stop_point_id"],
                "distance_meters": r["distance_meters"],
                "duration_seconds": r["duration_seconds"],
            }
            for r in rows
        }
    finally:
        conn.close()


def lookup_walk(walk_distances: dict[int, dict], station_index: int, rightmove_name: str) -> dict | None:
    """Returns the stored walk-data row for station_index, but only if its
    stored rightmove_name still matches the name currently at that index --
    guards against Rightmove having reordered nearest_stations_raw between
    the scrape that computed this row and now. Index-keying alone would
    otherwise silently attach the wrong station's distance/duration; CRS-
    keying degraded safely (no match = no data), so this restores that
    property. Shared by routes/commute.py and routes/listings.py so both
    apply the guard identically."""
    walk = walk_distances.get(station_index)
    if walk is None or walk["rightmove_name"] != rightmove_name:
        return None
    return walk
