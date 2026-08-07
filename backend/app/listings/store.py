"""Listing row read/write helpers, including the manual-edit stickiness rule:
a field name present in `edited_fields` was hand-corrected by the user and
must never be silently overwritten by a later scrape or job."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.connection import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_listing(listing_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_listings(user_status: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        if user_status:
            rows = conn.execute(
                "SELECT * FROM listings WHERE user_status = ? ORDER BY created_at DESC", (user_status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM listings ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_stub_listing(listing_id: int, url: str) -> None:
    now = _now_iso()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO listings (id, url, extraction_status, edited_fields, created_at, updated_at)
            VALUES (?, ?, 'queued', '{}', ?, ?)
            ON CONFLICT (id) DO NOTHING
            """,
            (listing_id, url, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def apply_extracted_fields(listing_id: int, fields: dict, from_scrape: bool = True) -> None:
    """Write extracted/derived fields onto a listing, skipping any field the
    user has manually edited (present in edited_fields). System columns
    (extraction_status, extraction_error, updated_at) are always written."""
    listing = get_listing(listing_id)
    if listing is None:
        raise ValueError(f"no listing with id {listing_id}")

    edited_fields = json.loads(listing["edited_fields"] or "{}")
    to_write = {k: v for k, v in fields.items() if not (from_scrape and k in edited_fields)}
    to_write["updated_at"] = _now_iso()

    if not to_write:
        return

    set_clause = ", ".join(f"{k} = ?" for k in to_write)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE listings SET {set_clause} WHERE id = ?",
            (*to_write.values(), listing_id),
        )
        conn.commit()
    finally:
        conn.close()


def apply_manual_edit(listing_id: int, fields: dict) -> dict:
    """User-initiated edit via PATCH: writes the fields and marks each one
    sticky in edited_fields so future scrapes/jobs never clobber it."""
    listing = get_listing(listing_id)
    if listing is None:
        raise ValueError(f"no listing with id {listing_id}")

    now = _now_iso()
    edited_fields = json.loads(listing["edited_fields"] or "{}")
    for key in fields:
        edited_fields[key] = now

    to_write = dict(fields)
    to_write["edited_fields"] = json.dumps(edited_fields)
    to_write["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in to_write)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE listings SET {set_clause} WHERE id = ?",
            (*to_write.values(), listing_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_listing(listing_id)


def set_user_status(listing_id: int, user_status: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE listings SET user_status = ?, updated_at = ? WHERE id = ?",
            (user_status, _now_iso(), listing_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_extraction_status(listing_id: int, status: str, error: str | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE listings SET extraction_status = ?, extraction_error = ?, updated_at = ? WHERE id = ?",
            (status, error, _now_iso(), listing_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_snapshot(listing_id: int, price_gbp: int | None, rightmove_status: str | None, raw: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO listing_snapshots (listing_id, captured_at, price_gbp, rightmove_status, raw_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (listing_id, _now_iso(), price_gbp, rightmove_status, json.dumps(raw)),
        )
        conn.commit()
    finally:
        conn.close()


def latest_snapshot_raw(listing_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT raw_json FROM listing_snapshots WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
            (listing_id,),
        ).fetchone()
        return json.loads(row["raw_json"]) if row else None
    finally:
        conn.close()


def delete_listing(listing_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM commute_data WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM mortgage_scenarios WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM listing_snapshots WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM jobs WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        conn.commit()
    finally:
        conn.close()
