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

# Backoff after a failed attempt, keyed by the job's attempts count at the
# time it's considered for re-claiming. Without this, a requeued job (oldest
# created_at) gets picked again on the very next poll, so a single transient
# failure (e.g. a 30s Rightmove hiccup) burns the entire retry budget in a
# couple of seconds instead of actually waiting out the transient condition.
_BACKOFF_SECONDS_BY_ATTEMPTS = {1: 10, 2: 30}


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


def has_pending_job(listing_id: int, job_type: str) -> bool:
    """True if a queued or running job of this type already exists for this
    listing. Used to guard against enqueueing duplicates on repeated/rapid
    refresh requests."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM jobs
            WHERE listing_id = ? AND job_type = ? AND status IN ('queued', 'running')
            LIMIT 1
            """,
            (listing_id, job_type),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def claim_next_job(lane: str) -> dict | None:
    """Atomically claim the oldest eligible queued job in this lane: queued,
    either has no dependency or its dependency job is done, and — if it's
    been retried before — has waited out its backoff window since the last
    failure. Returns the claimed job row as a dict, or None if nothing is
    eligible right now."""
    now = datetime.now(timezone.utc)
    lease_expires = (now + timedelta(seconds=LEASE_SECONDS)).isoformat()
    now_iso = now.isoformat()

    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        candidates = conn.execute(
            """
            SELECT j.id, j.attempts, j.updated_at FROM jobs j
            WHERE j.lane = ? AND j.status = 'queued'
              AND (
                j.depends_on_job_id IS NULL
                OR EXISTS (SELECT 1 FROM jobs d WHERE d.id = j.depends_on_job_id AND d.status = 'done')
              )
            ORDER BY j.created_at ASC
            """,
            (lane,),
        ).fetchall()

        job_id = None
        for candidate in candidates:
            backoff = _BACKOFF_SECONDS_BY_ATTEMPTS.get(candidate["attempts"], 0)
            if backoff == 0:
                job_id = candidate["id"]
                break
            elapsed = (now - datetime.fromisoformat(candidate["updated_at"])).total_seconds()
            if elapsed >= backoff:
                job_id = candidate["id"]
                break

        if job_id is None:
            conn.execute("COMMIT")
            return None

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


def renew_lease(job_id: int) -> bool:
    """Extend a still-running job's lease so the reclaim loop doesn't steal
    it out from under an active (just slow) handler. Only takes effect if the
    job is still 'running' under this claim — if it's already been reclaimed
    and re-claimed by another worker, this is a harmless no-op rather than
    something that could extend a lease that no longer belongs to the caller."""
    now = datetime.now(timezone.utc)
    lease_expires = (now + timedelta(seconds=LEASE_SECONDS)).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE jobs SET heartbeat_at = ?, lease_expires_at = ? WHERE id = ? AND status = 'running'",
            (now.isoformat(), lease_expires, job_id),
        )
        conn.commit()
        return cur.rowcount > 0
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


def fail_job(job_id: int, error: str, permanent: bool = False) -> None:
    """Mark a job failed. If it still has attempts left (and the failure
    isn't marked permanent — e.g. no handler exists for this job_type, so
    retrying can never succeed), requeue it instead of leaving it
    permanently failed. The attempts read and the status write happen in one
    BEGIN IMMEDIATE transaction so a concurrent reclaim/claim of the same job
    can't interleave with this read-modify-write."""
    now = _now_iso()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT attempts FROM jobs WHERE id = ?", (job_id,)).fetchone()
        attempts = row["attempts"] if row else MAX_ATTEMPTS
        next_status = "failed" if permanent or attempts >= MAX_ATTEMPTS else "queued"
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
    covers a worker that died mid-job without failing it explicitly. Clears
    the stale heartbeat/lease columns too, so the row doesn't carry misleading
    values from the previous (dead) claim."""
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE jobs SET status = 'queued', updated_at = ?, heartbeat_at = NULL, lease_expires_at = NULL
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


def latest_job_statuses_for_listings(listing_ids: list[int]) -> dict[int, dict[str, str]]:
    """For each given listing, returns {job_type: status} using only each
    job_type's most recent row (a listing accumulates one row per job_type
    per Refresh/backfill — see pipeline_status.py). One aggregate query
    regardless of how many listing_ids are passed, so callers like
    list_listings can compute a per-listing pipeline status without an N+1
    query per row."""
    if not listing_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in listing_ids)
        rows = conn.execute(
            f"""
            SELECT j.listing_id, j.job_type, j.status
            FROM jobs j
            JOIN (
                SELECT listing_id, job_type, MAX(id) AS max_id
                FROM jobs
                WHERE listing_id IN ({placeholders})
                GROUP BY listing_id, job_type
            ) latest ON j.id = latest.max_id
            """,
            listing_ids,
        ).fetchall()
        result: dict[int, dict[str, str]] = {}
        for row in rows:
            result.setdefault(row["listing_id"], {})[row["job_type"]] = row["status"]
        return result
    finally:
        conn.close()
