"""Plain CRUD for destination_journeys (migration 0014). A listing's rows
are deleted and reinserted wholesale on each recompute, not upserted
individually -- same precedent as app/commute/walk_store.py."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection


def replace_journeys(listing_id: int, rows: list[dict]) -> None:
    """rows: [{"destination_id", "duration_minutes", "kind", "num_changes",
    "operator", "origin_crs", "origin_name", "arrival_name",
    "interchange_crs", "departure_time", "arrival_time"}]."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM destination_journeys WHERE listing_id = ?", (listing_id,))
        conn.executemany(
            "INSERT INTO destination_journeys "
            "(listing_id, destination_id, duration_minutes, kind, num_changes, operator, "
            "origin_crs, origin_name, arrival_name, interchange_crs, departure_time, arrival_time, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    r.get("arrival_name"),
                    r.get("interchange_crs"),
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


def replace_single(listing_id: int, destination_id: int, row: dict | None) -> None:
    """Delete-then-reinsert for exactly one (listing_id, destination_id)
    pair, leaving every other destination's stored row for this listing
    untouched -- used by compute_for_destination's per-destination backfill,
    where replace_journeys' whole-listing wipe would be wrong (it would
    discard every other destination's already-computed result). `row` is
    the same shape as replace_journeys' row dicts, minus "destination_id"
    (redundant with the argument); None just clears the row."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM destination_journeys WHERE listing_id = ? AND destination_id = ?",
            (listing_id, destination_id),
        )
        if row is not None:
            conn.execute(
                "INSERT INTO destination_journeys "
                "(listing_id, destination_id, duration_minutes, kind, num_changes, operator, "
                "origin_crs, origin_name, arrival_name, interchange_crs, departure_time, arrival_time, computed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    listing_id,
                    destination_id,
                    row["duration_minutes"],
                    row["kind"],
                    row["num_changes"],
                    row["operator"],
                    row["origin_crs"],
                    row["origin_name"],
                    row.get("arrival_name"),
                    row.get("interchange_crs"),
                    row["departure_time"],
                    row["arrival_time"],
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def delete_for_destination(listing_id: int, destination_id: int) -> None:
    replace_single(listing_id, destination_id, None)


def set_home_journey(destination_id: int, journey: dict | None) -> None:
    """journey: {"duration_minutes", "kind", "num_changes"} (extra keys, e.g.
    from a full _journey_row dict, are ignored) -- or None to clear. Same
    delete-then-reinsert precedent as replace_single, just keyed by
    destination_id alone since home has one row per destination, not per
    listing."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM home_journeys WHERE destination_id = ?", (destination_id,))
        if journey is not None:
            conn.execute(
                "INSERT INTO home_journeys (destination_id, duration_minutes, kind, num_changes, computed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (destination_id, journey["duration_minutes"], journey["kind"], journey["num_changes"], now),
            )
        conn.commit()
    finally:
        conn.close()


def get_home_journeys() -> dict[int, dict]:
    """Returns {destination_id: row_dict} for every destination with a
    stored home journey."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM home_journeys").fetchall()
        return {r["destination_id"]: dict(r) for r in rows}
    finally:
        conn.close()


def delete_home_journey(destination_id: int) -> None:
    set_home_journey(destination_id, None)
