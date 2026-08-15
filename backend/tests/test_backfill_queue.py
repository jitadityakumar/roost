import threading
import time

import pytest

from app.destinations import backfill_queue, backfill_status, compute

# conftest.py's autouse isolated_db fixture clears backfill_status._runs and
# waits for backfill_queue to drain after every test, so these tests don't
# need their own reset/teardown fixture.


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_two_destinations_enqueued_together_run_one_at_a_time(monkeypatch):
    """The whole point of serializing backfills: a second destination
    enqueued while the first is still in flight must stay 'queued' (not
    start running) until the first finishes -- proving they never run
    concurrently against train-journey-planner."""
    first_release = threading.Event()
    order = []

    def fake_compute(destination_id):
        order.append(("start", destination_id))
        if destination_id == 1:
            first_release.wait(timeout=2.0)
        order.append(("end", destination_id))

    monkeypatch.setattr(compute, "compute_for_destination", fake_compute)

    backfill_queue.enqueue(1, total=5)
    backfill_queue.enqueue(2, total=5)

    assert _wait_for(lambda: backfill_status.get(1)["status"] == "running")
    # Destination 2 must not have started yet -- it's queued behind 1.
    assert backfill_status.get(2)["status"] == "queued"
    assert order == [("start", 1)]

    first_release.set()

    assert _wait_for(lambda: backfill_status.get(2) is not None and backfill_status.get(2)["status"] == "running")
    backfill_queue.wait_until_idle()
    assert order == [("start", 1), ("end", 1), ("start", 2), ("end", 2)]


def test_enqueue_while_already_queued_or_running_collapses_to_one_rerun(monkeypatch):
    """N rapid edits to the same destination while its backfill is already
    in flight must produce exactly one rerun once it finishes, not one per
    edit -- same dedup guarantee the pre-queue per-destination design had."""
    release = threading.Event()
    calls = []

    def fake_compute(destination_id):
        calls.append(destination_id)
        release.wait(timeout=2.0)

    monkeypatch.setattr(compute, "compute_for_destination", fake_compute)

    backfill_queue.enqueue(1, total=5)
    assert _wait_for(lambda: backfill_status.get(1)["status"] == "running")

    # Three rapid re-enqueues while the first call is still blocked.
    backfill_queue.enqueue(1, total=5)
    backfill_queue.enqueue(1, total=5)
    backfill_queue.enqueue(1, total=5)

    release.set()
    backfill_queue.wait_until_idle()

    # The first call, plus exactly one rerun -- not four.
    assert calls == [1, 1]


def test_wait_until_idle_returns_immediately_when_nothing_queued():
    started = time.monotonic()
    backfill_queue.wait_until_idle(timeout=2.0)
    assert time.monotonic() - started < 0.5


def test_a_failed_backfill_does_not_block_later_destinations(monkeypatch):
    def fake_compute(destination_id):
        if destination_id == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(compute, "compute_for_destination", fake_compute)

    backfill_queue.enqueue(1, total=1)
    backfill_queue.enqueue(2, total=1)
    backfill_queue.wait_until_idle()

    # compute_for_destination itself is responsible for calling
    # backfill_status.finish(..., "failed") before re-raising -- the fake
    # here skips that (it's testing the worker loop, not compute.py), so
    # destination 1's tracked status is left at whatever start() set. What
    # matters for this test is that destination 2 still ran to completion
    # despite destination 1's exception.
    assert backfill_status.get(2)["status"] == "running"
