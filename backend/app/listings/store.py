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


def create_stub_listing(listing_id: int, url: str) -> bool:
    """Returns True if this call actually inserted the row (i.e. this is the
    first submission of this listing), False if it already existed. Callers
    use this to avoid enqueueing a duplicate extraction job when two
    concurrent submissions race for the same new URL."""
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO listings (id, url, extraction_status, edited_fields, created_at, updated_at)
            VALUES (?, ?, 'queued', '{}', ?, ?)
            ON CONFLICT (id) DO NOTHING
            """,
            (listing_id, url, now, now),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def apply_extracted_fields(listing_id: int, fields: dict, from_scrape: bool = True) -> None:
    """Write extracted/derived fields onto a listing, skipping any field the
    user has manually edited (present in edited_fields). System columns
    (extraction_status, extraction_error, updated_at) are always written.

    The read of edited_fields and the write both happen inside one
    BEGIN IMMEDIATE transaction on a single connection: without that, a
    concurrent apply_manual_edit could mark a field sticky *after* this
    function already decided (from a stale read) that the field was safe to
    overwrite, permanently baking a scraped value in over a value the user
    just corrected. BEGIN IMMEDIATE serializes against apply_manual_edit's
    own BEGIN IMMEDIATE below, so that interleaving can't happen.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT edited_fields FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if row is None:
            conn.execute("COMMIT")
            raise ValueError(f"no listing with id {listing_id}")

        edited_fields = json.loads(row["edited_fields"] or "{}")
        to_write = {k: v for k, v in fields.items() if not (from_scrape and k in edited_fields)}
        to_write["updated_at"] = _now_iso()

        set_clause = ", ".join(f"{k} = ?" for k in to_write)
        conn.execute(
            f"UPDATE listings SET {set_clause} WHERE id = ?",
            (*to_write.values(), listing_id),
        )
        conn.commit()
    finally:
        conn.close()


def apply_manual_edit(listing_id: int, fields: dict) -> dict:
    """User-initiated edit via PATCH: writes the fields and marks each one
    sticky in edited_fields so future scrapes/jobs never clobber it.

    Read-then-write on edited_fields happens inside one BEGIN IMMEDIATE
    transaction (see apply_extracted_fields docstring) so two concurrent
    manual edits can't lose each other's sticky markers via a last-write-wins
    JSON merge.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT edited_fields FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if row is None:
            conn.execute("COMMIT")
            raise ValueError(f"no listing with id {listing_id}")

        now = _now_iso()
        edited_fields = json.loads(row["edited_fields"] or "{}")
        for key in fields:
            edited_fields[key] = now

        to_write = dict(fields)
        to_write["edited_fields"] = json.dumps(edited_fields)
        to_write["updated_at"] = now

        set_clause = ", ".join(f"{k} = ?" for k in to_write)
        conn.execute(
            f"UPDATE listings SET {set_clause} WHERE id = ?",
            (*to_write.values(), listing_id),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


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
