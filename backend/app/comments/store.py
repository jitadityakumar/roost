"""Per-listing comments, including rejection reasons (comment_type
'rejection', written by app.listings.store.set_user_status). See migration
0025 for why created_at/updated_at are nullable -- backfilled rows from the
old comment/rejection_reason columns carry NULL there, not a synthetic
timestamp."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_comments(listing_id: int) -> list[dict]:
    """Most-recent-first. The `id DESC` tiebreak matters because created_at
    is nullable: SQLite sorts NULLs last under DESC regardless, so real
    (non-null) rows always outrank backfilled ones by id order, not by
    accident of NULL ordering alone."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM comments WHERE listing_id = ? ORDER BY created_at DESC, id DESC",
            (listing_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_comment(comment_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_comment(listing_id: int, comment_type: str, text: str, initials: str | None) -> dict:
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO comments (listing_id, comment_type, text, initials, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (listing_id, comment_type, text, initials, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_comment(comment_id: int, text: str, initials: str | None) -> dict | None:
    """Leaves created_at and comment_type untouched. None if no such comment."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE comments SET text = ?, initials = ?, updated_at = ? WHERE id = ?",
            (text, initials, _now_iso(), comment_id),
        )
        if cur.rowcount == 0:
            conn.commit()
            return None
        conn.commit()
        row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_comment(comment_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
    finally:
        conn.close()
