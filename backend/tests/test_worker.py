import asyncio

import pytest

from app.jobs import queue, worker
from app.jobs.llm_client import LlmCallError
from app.listings import store


@pytest.fixture
def listing_id():
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    return 1


def test_llm_pool_treats_permanent_llm_call_error_as_non_retryable(listing_id, monkeypatch):
    queue.enqueue_job(listing_id, "text_extract", "llm")
    job = queue.claim_next_job("llm")

    def boom(job):
        raise LlmCallError("claude CLI not found on PATH", permanent=True)

    monkeypatch.setitem(worker.HANDLERS, "text_extract", boom)

    pool = worker.LlmLaneWorkerPool()
    asyncio.run(pool._run_one_job(job))

    jobs = queue.get_jobs_for_listing(listing_id)
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["attempts"] == 1  # permanent failure skips the retry budget


def test_llm_pool_retries_transient_llm_call_error(listing_id, monkeypatch):
    queue.enqueue_job(listing_id, "text_extract", "llm")
    job = queue.claim_next_job("llm")

    def boom(job):
        raise LlmCallError("no parseable JSON in claude output")

    monkeypatch.setitem(worker.HANDLERS, "text_extract", boom)

    pool = worker.LlmLaneWorkerPool()
    asyncio.run(pool._run_one_job(job))

    jobs = queue.get_jobs_for_listing(listing_id)
    assert jobs[0]["status"] == "queued"  # requeued, retry budget not exhausted


def test_llm_pool_completes_job_on_success(listing_id, monkeypatch):
    queue.enqueue_job(listing_id, "text_extract", "llm")
    job = queue.claim_next_job("llm")

    monkeypatch.setitem(worker.HANDLERS, "text_extract", lambda job: None)

    pool = worker.LlmLaneWorkerPool()
    asyncio.run(pool._run_one_job(job))

    assert queue.get_jobs_for_listing(listing_id)[0]["status"] == "done"
