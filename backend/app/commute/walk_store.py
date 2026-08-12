"""Plain CRUD for station_walk_distances (migration 0011). Rows for a
listing are deleted and reinserted wholesale on each recompute, not
upserted individually -- see context.md's "Station walking distance"
section."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection


def replace_walk_distances(listing_id: int, rows: list[dict]) -> None:
    """rows: [{"crs": str, "distance_meters": int, "duration_seconds": int}]."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM station_walk_distances WHERE listing_id = ?", (listing_id,))
        conn.executemany(
            "INSERT INTO station_walk_distances "
            "(listing_id, crs, distance_meters, duration_seconds, computed_at) VALUES (?, ?, ?, ?, ?)",
            [(listing_id, r["crs"], r["distance_meters"], r["duration_seconds"], now) for r in rows],
        )
        conn.commit()
    finally:
        conn.close()


def get_walk_distances(listing_id: int) -> dict[str, dict]:
    """Returns {crs: {"distance_meters": ..., "duration_seconds": ...}}."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT crs, distance_meters, duration_seconds FROM station_walk_distances WHERE listing_id = ?",
            (listing_id,),
        ).fetchall()
        return {r["crs"]: {"distance_meters": r["distance_meters"], "duration_seconds": r["duration_seconds"]} for r in rows}
    finally:
        conn.close()
