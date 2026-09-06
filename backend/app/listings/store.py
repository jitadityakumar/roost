"""Listing row read/write helpers, including the manual-edit stickiness rule:
a field name present in `edited_fields` was hand-corrected by the user and
must never be silently overwritten by a later scrape or job — and neither
must its companion `_source` column (see FIELD_SOURCE_COMPANIONS)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.comments import store as comments_store
from app.db.connection import get_connection

# Every multi-source field's companion `_source` column. A manual edit to
# the value column freezes the value (via edited_fields), but the source
# column is a separate dict key that would otherwise keep getting reset to
# 'rightmove'/'llm' by every future scrape or job — falsely re-claiming an
# automated origin for a value the user has since overridden by hand. When
# the value field is sticky, its source companion must be sticky too.
FIELD_SOURCE_COMPANIONS = {
    "lease_years_remaining": "lease_years_remaining_source",
    "service_charge_pa": "service_charge_source",
    "service_charge_pm": "service_charge_source",
    "council_tax_band": "council_tax_band_source",
    "floor_area_sqft": "floor_area_sqft_source",
    "epc_current": "epc_source",
    "epc_potential": "epc_source",
    "chain_free": "chain_free_source",
    "cash_only": "cash_only_source",
    "garden": "garden_source",
    "parking": "parking_source",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_sticky(key: str, edited_fields: dict) -> bool:
    if key in edited_fields:
        return True
    return any(
        key == source_field and value_field in edited_fields
        for value_field, source_field in FIELD_SOURCE_COMPANIONS.items()
    )


def target_fields_all_sticky(listing_id: int, field_names: list[str]) -> bool:
    """True if every field in field_names is already sticky (hand-edited, or
    the value-field companion of a sticky _source column) for this listing.
    Used by the LLM job-enqueue efficiency check (see llm_enqueue.py) —
    a job-level check, since e.g. text_extract populates several fields
    atomically and should only be skipped if ALL of them are already
    hand-edited, not just one."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT edited_fields FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if row is None:
            raise ValueError(f"no listing with id {listing_id}")
        edited_fields = json.loads(row["edited_fields"] or "{}")
        return all(_is_sticky(f, edited_fields) for f in field_names)
    finally:
        conn.close()


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
        to_write = {k: v for k, v in fields.items() if not (from_scrape and _is_sticky(k, edited_fields))}
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


# Maps a target user_status to the comment_type its mandatory-comment row
# gets (issue #82). 'rejected' keeps the pre-existing 'rejection' type name
# for continuity with data written before this map existed; 'viewing'/
# 'contacted' just reuse the status name.
STATUS_COMMENT_TYPE = {"rejected": "rejection", "viewing": "viewing", "contacted": "contacted"}


def set_user_status(
    listing_id: int, user_status: str, comment: str | None = None, initials: str | None = None
) -> None:
    """comment is only written when provided (i.e. the caller is moving into
    a status that requires one) -- as a new comments row typed via
    STATUS_COMMENT_TYPE, not a column write. Moving away from that status
    later leaves the row untouched -- kept as history rather than cleared,
    so it's still visible if the listing re-enters the same status or the
    past note is worth revisiting; re-entering appends a second row of that
    type rather than overwriting the first.

    Not atomic: the user_status UPDATE and the comments INSERT are two
    statements on two separate connections (comments_store.create_comment
    opens its own) -- a crash between them would leave user_status set with
    no matching comment. Same risk profile as every other cross-table write
    in this module (e.g. delete_listing's six sequential deletes), not worth
    a shared transaction for a single-user hobby app.
    """
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE listings SET user_status = ?, updated_at = ? WHERE id = ?",
            (user_status, _now_iso(), listing_id),
        )
        conn.commit()
    finally:
        conn.close()
    if comment is not None:
        comments_store.create_comment(listing_id, STATUS_COMMENT_TYPE[user_status], comment, initials)


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
        conn.execute("DELETE FROM mortgage_scenarios WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM listing_snapshots WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM jobs WHERE listing_id = ?", (listing_id,))
        # station_walk_distances (0011), destination_journeys (0014), and
        # journey_scan_pools (0021) all have a NOT NULL, non-cascading FK on
        # listings(id) -- with PRAGMA foreign_keys=ON this delete would
        # otherwise raise IntegrityError for any listing that has ever had a
        # walk distance or frequent-destination journey computed (i.e. most
        # listings, since both now run automatically at scrape time).
        conn.execute("DELETE FROM station_walk_distances WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM destination_journeys WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM journey_scan_pools WHERE listing_id = ?", (listing_id,))
        # comments (0025) is also a NOT NULL, non-cascading FK on
        # listings(id) -- same failure mode as the tables above.
        conn.execute("DELETE FROM comments WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        conn.commit()
    finally:
        conn.close()
