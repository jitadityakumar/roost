from datetime import datetime, timedelta, timezone

from app.db.connection import get_connection
from app.jobs import queue
from app.listings import store


def _make_listing(listing_id=1):
    store.create_stub_listing(listing_id, f"https://www.rightmove.co.uk/properties/{listing_id}")
    return listing_id


def _age_job(job_id, seconds_ago):
    """Back-date a job's updated_at so backoff-window tests don't need to
    sleep for real."""
    ts = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    conn = get_connection()
    try:
        conn.execute("UPDATE jobs SET updated_at = ? WHERE id = ?", (ts, job_id))
        conn.commit()
    finally:
        conn.close()


def test_enqueue_and_claim():
    listing_id = _make_listing()
    job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")

    job = queue.claim_next_job("http")

    assert job["id"] == job_id
    assert job["status"] == "running"
    assert job["attempts"] == 1


def test_claim_respects_lane():
    listing_id = _make_listing()
    queue.enqueue_job(listing_id, "rightmove_extract", "http")

    assert queue.claim_next_job("llm") is None


def test_claim_skips_job_with_unfinished_dependency():
    listing_id = _make_listing()
    parent_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")
    queue.enqueue_job(listing_id, "media_download", "http", depends_on_job_id=parent_id)

    first = queue.claim_next_job("http")
    assert first["id"] == parent_id

    # media_download still blocked: parent claimed but not done yet.
    assert queue.claim_next_job("http") is None

    queue.complete_job(parent_id)
    second = queue.claim_next_job("http")
    assert second["job_type"] == "media_download"


def test_claim_is_fifo():
    listing_id = _make_listing()
    first_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")
    _age_job(first_id, seconds_ago=5)
    second_id = queue.enqueue_job(listing_id, "media_download", "http")

    claimed = queue.claim_next_job("http")
    assert claimed["id"] == first_id
    assert second_id  # sanity: distinct row exists


def test_has_pending_job():
    listing_id = _make_listing()
    assert queue.has_pending_job(listing_id, "rightmove_extract") is False

    queue.enqueue_job(listing_id, "rightmove_extract", "http")
    assert queue.has_pending_job(listing_id, "rightmove_extract") is True


def test_fail_job_requeues_within_backoff_window():
    listing_id = _make_listing()
    job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")
    queue.claim_next_job("http")

    queue.fail_job(job_id, "transient error")

    # attempts == 1 -> 10s backoff, and updated_at is "now", so it should
    # not be eligible yet.
    assert queue.claim_next_job("http") is None


def test_fail_job_requeues_after_backoff_elapses():
    listing_id = _make_listing()
    job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")
    queue.claim_next_job("http")
    queue.fail_job(job_id, "transient error")

    _age_job(job_id, seconds_ago=15)  # past the 10s backoff for attempts=1

    claimed = queue.claim_next_job("http")
    assert claimed["id"] == job_id
    assert claimed["attempts"] == 2


def test_fail_job_permanent_skips_retry():
    listing_id = _make_listing()
    job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")
    queue.claim_next_job("http")

    queue.fail_job(job_id, "no handler for job_type", permanent=True)

    jobs = queue.get_jobs_for_listing(listing_id)
    assert jobs[0]["status"] == "failed"


def test_fail_job_marks_failed_after_max_attempts():
    listing_id = _make_listing()
    job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")

    for attempt in range(queue.MAX_ATTEMPTS):
        claimed = queue.claim_next_job("http")
        assert claimed is not None, f"expected a claimable job on attempt {attempt + 1}"
        queue.fail_job(job_id, "still failing")
        _age_job(job_id, seconds_ago=60)

    jobs = queue.get_jobs_for_listing(listing_id)
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["attempts"] == queue.MAX_ATTEMPTS


def test_reclaim_stale_leases():
    listing_id = _make_listing()
    job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")
    queue.claim_next_job("http")

    conn = get_connection()
    try:
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        conn.execute("UPDATE jobs SET lease_expires_at = ? WHERE id = ?", (expired, job_id))
        conn.commit()
    finally:
        conn.close()

    reclaimed_count = queue.reclaim_stale_leases()

    assert reclaimed_count == 1
    jobs = queue.get_jobs_for_listing(listing_id)
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["lease_expires_at"] is None
