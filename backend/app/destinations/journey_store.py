"""Plain CRUD for destination_journeys (migration 0014). A listing's rows
are deleted and reinserted wholesale on each recompute, not upserted
individually -- same precedent as app/commute/walk_store.py."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection


def replace_journeys(listing_id: int, rows: list[dict]) -> None:
    """rows: [{"destination_id", "duration_minutes", "kind", "num_changes",
    "operator", "origin_crs", "origin_name", "departure_time",
    "arrival_time"}]."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM destination_journeys WHERE listing_id = ?", (listing_id,))
        conn.executemany(
            "INSERT INTO destination_journeys "
            "(listing_id, destination_id, duration_minutes, kind, num_changes, operator, "
            "origin_crs, origin_name, departure_time, arrival_time, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    listing_id,
                    r["destination_id"],
                    r["duration_minutes"],
                    r["kind"],
                    r["num_changes"],
                    r["operator"],
                    r["origin_crs"],
                    r["origin_name"],
                    r["departure_time"],
                    r["arrival_time"],
                    now,
                )
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_journeys(listing_id: int) -> dict[int, dict]:
    """Returns {destination_id: row_dict}."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM destination_journeys WHERE listing_id = ?", (listing_id,)
        ).fetchall()
        return {r["destination_id"]: dict(r) for r in rows}
    finally:
        conn.close()
