"""jobs table CRUD: enqueue, atomically claim, heartbeat, complete/fail,
and stale-lease reclaim.

Two writers touch this table (the FastAPI process enqueuing jobs, and the
in-process worker pool claiming/updating them) — every write here goes
through its own short-lived connection so WAL + busy_timeout (set in
connection.py) handle the concurrency, not manual locking.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.connection import get_connection

LEASE_SECONDS = 120
MAX_ATTEMPTS = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_job(listing_id: int, job_type: str, lane: str, depends_on_job_id: int | None = None) -> int:
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO jobs (listing_id, job_type, lane, status, depends_on_job_id, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?, ?)
            """,
            (listing_id, job_type, lane, depends_on_job_id, now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def claim_next_job(lane: str) -> dict | None:
    """Atomically claim the oldest eligible queued job in this lane: queued,
    and either has no dependency or its dependency job is done. Returns the
    claimed job row as a dict, or None if nothing is eligible."""
    now = datetime.now(timezone.utc)
    lease_expires = (now + timedelta(seconds=LEASE_SECONDS)).isoformat()
    now_iso = now.isoformat()

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT j.id FROM jobs j
            WHERE j.lane = ? AND j.status = 'queued'
              AND (
                j.depends_on_job_id IS NULL
                OR EXISTS (SELECT 1 FROM jobs d WHERE d.id = j.depends_on_job_id AND d.status = 'done')
              )
            ORDER BY j.created_at ASC
            LIMIT 1
            """,
            (lane,),
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None

        job_id = row["id"]
        conn.execute(
            """
            UPDATE jobs SET status = 'running', attempts = attempts + 1,
                heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now_iso, lease_expires, now_iso, job_id),
        )
        conn.commit()

        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(job)
    finally:
        conn.close()


def complete_job(job_id: int) -> None:
    now = _now_iso()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE jobs SET status = 'done', updated_at = ?, heartbeat_at = ? WHERE id = ?",
            (now, now, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def fail_job(job_id: int, error: str) -> None:
    """Mark a job failed. If it still has attempts left, requeue it instead
    of leaving it permanently failed (transient failures, e.g. an offline
    LLM host, shouldn't burn the whole retry budget on the first try)."""
    now = _now_iso()
    conn = get_connection()
    try:
        row = conn.execute("SELECT attempts FROM jobs WHERE id = ?", (job_id,)).fetchone()
        attempts = row["attempts"] if row else MAX_ATTEMPTS
        next_status = "queued" if attempts < MAX_ATTEMPTS else "failed"
        conn.execute(
            """
            UPDATE jobs SET status = ?, last_error = ?, updated_at = ?,
                heartbeat_at = NULL, lease_expires_at = NULL
            WHERE id = ?
            """,
            (next_status, error, now, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def reclaim_stale_leases() -> int:
    """Return any 'running' job whose lease has expired back to 'queued' —
    covers a worker that died mid-job without failing it explicitly."""
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE jobs SET status = 'queued', updated_at = ?
            WHERE status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (now, now),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_jobs_for_listing(listing_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE listing_id = ? ORDER BY created_at ASC", (listing_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
