"""Plain CRUD for frequent_destinations (migration 0013) -- admin-defined
places the user travels to often, see GitHub issue #28. Deliberately
without listings/store.py's BEGIN IMMEDIATE concurrency guard, same
reasoning as app/standards/store.py: only ever written from the
single-user admin UI, no background worker racing against it."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.db.connection import get_connection

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_time(time: str) -> None:
    if not _TIME_RE.match(time):
        raise ValueError(f"time {time!r} is not a valid 24h HH:MM time")


def _validate_day_of_week(day_of_week: int) -> None:
    if not isinstance(day_of_week, int) or not (0 <= day_of_week <= 6):
        raise ValueError(f"day_of_week {day_of_week!r} must be an integer 0 (Monday) .. 6 (Sunday)")


def _validate_destination_type(destination_type: str) -> None:
    if destination_type not in ("station", "postcode"):
        raise ValueError(f"destination_type {destination_type!r} must be 'station' or 'postcode'")


def list_destinations() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM frequent_destinations ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_destination(
    name: str, destination_type: str, tfl_identifier: str, station_name: str, day_of_week: int, time: str
) -> dict:
    if not name.strip():
        raise ValueError("name is required")
    _validate_destination_type(destination_type)
    _validate_day_of_week(day_of_week)
    _validate_time(time)
    conn = get_connection()
    try:
        now = _now_iso()
        cur = conn.execute(
            "INSERT INTO frequent_destinations "
            "(name, destination_type, tfl_identifier, station_name, day_of_week, time, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (name.strip(), destination_type, tfl_identifier.strip(), station_name.strip(), day_of_week, time, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM frequent_destinations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_destination(destination_id: int, **changes) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM frequent_destinations WHERE id = ?", (destination_id,)).fetchone()
        if row is None:
            return None
        merged = dict(row)
        merged.update({k: v for k, v in changes.items() if v is not None})

        if "day_of_week" in changes:
            _validate_day_of_week(merged["day_of_week"])
        if "time" in changes:
            _validate_time(merged["time"])
        if "name" in changes:
            if not str(merged["name"]).strip():
                raise ValueError("name is required")
            merged["name"] = str(merged["name"]).strip()
        if "destination_type" in changes:
            _validate_destination_type(merged["destination_type"])
        if "tfl_identifier" in changes:
            merged["tfl_identifier"] = str(merged["tfl_identifier"]).strip()
        if "station_name" in changes:
            merged["station_name"] = str(merged["station_name"]).strip()

        to_write = {
            k: merged[k]
            for k in ("name", "destination_type", "tfl_identifier", "station_name", "day_of_week", "time", "enabled")
        }
        set_clause = ", ".join(f"{k} = ?" for k in to_write)
        conn.execute(
            f"UPDATE frequent_destinations SET {set_clause} WHERE id = ?",
            (*to_write.values(), destination_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM frequent_destinations WHERE id = ?", (destination_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_destination(destination_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM destination_journeys WHERE destination_id = ?", (destination_id,))
        conn.execute("DELETE FROM home_journeys WHERE destination_id = ?", (destination_id,))
        conn.execute("DELETE FROM frequent_destinations WHERE id = ?", (destination_id,))
        conn.commit()
    finally:
        conn.close()
