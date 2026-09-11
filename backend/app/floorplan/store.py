from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.connection import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_trace_row(row) -> dict:
    out = dict(row)
    out["rooms"] = json.loads(out.pop("rooms_json"))
    out["shapes"] = json.loads(out.pop("shapes_json"))
    return out


def get_baseline() -> dict:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM floorplan_baseline WHERE id = 1").fetchone()
        return _load_trace_row(row)
    finally:
        conn.close()


def put_baseline(
    image_blob: str | None,
    image_w: int | None,
    image_h: int | None,
    active_scale: float | None,
    rooms: list[dict],
    shapes: list[dict],
) -> dict:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE floorplan_baseline SET
                image_blob = ?, image_w = ?, image_h = ?, active_scale = ?,
                rooms_json = ?, shapes_json = ?, updated_at = ?
            WHERE id = 1
            """,
            (image_blob, image_w, image_h, active_scale, json.dumps(rooms), json.dumps(shapes), _now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM floorplan_baseline WHERE id = 1").fetchone()
        return _load_trace_row(row)
    finally:
        conn.close()


def get_listing_trace(listing_id: int, image_path: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM listing_floorplan_traces WHERE listing_id = ? AND image_path = ?",
            (listing_id, image_path),
        ).fetchone()
        return _load_trace_row(row) if row else None
    finally:
        conn.close()


def list_listing_traces(listing_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM listing_floorplan_traces WHERE listing_id = ? ORDER BY image_path ASC",
            (listing_id,),
        ).fetchall()
        return [_load_trace_row(r) for r in rows]
    finally:
        conn.close()


def get_active_trace(listing_id: int) -> dict | None:
    """The trace shown for a listing's comparison, when it has traces
    against more than one floor plan image: whichever trace has ≥1 shape
    and was most recently updated. Most listings only ever get one image
    traced, so this only matters for the multi-floorplan-image case."""
    traces = [t for t in list_listing_traces(listing_id) if t["shapes"]]
    if not traces:
        return None
    return max(traces, key=lambda t: t["updated_at"])


def put_listing_trace(
    listing_id: int,
    image_path: str,
    image_w: int | None,
    image_h: int | None,
    active_scale: float | None,
    rooms: list[dict],
    shapes: list[dict],
) -> dict:
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO listing_floorplan_traces
                (listing_id, image_path, image_w, image_h, active_scale, rooms_json, shapes_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(listing_id, image_path) DO UPDATE SET
                image_w = excluded.image_w, image_h = excluded.image_h,
                active_scale = excluded.active_scale, rooms_json = excluded.rooms_json,
                shapes_json = excluded.shapes_json, updated_at = excluded.updated_at
            """,
            (listing_id, image_path, image_w, image_h, active_scale, json.dumps(rooms), json.dumps(shapes), now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM listing_floorplan_traces WHERE listing_id = ? AND image_path = ?",
            (listing_id, image_path),
        ).fetchone()
        return _load_trace_row(row)
    finally:
        conn.close()
