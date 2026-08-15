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


def test_concurrent_enqueue_during_finish_does_not_duplicate_a_run(monkeypatch):
    """Regression test (review finding on this PR): compute_for_destination
    calls backfill_status.finish() -- marking the run terminal -- before
    control returns to the worker. An earlier draft of backfill_queue
    gated "is this destination already active" on backfill_status's own
    state, which left a window right after finish() where a concurrent
    enqueue() for the same destination_id would see a terminal status and
    start a second, fully independent run instead of collapsing into the
    single pending rerun -- doubling that destination's whole-listing
    backfill. backfill_queue now gates on its own `_active` set instead,
    mutated atomically alongside the rerun decision, so this can't happen
    regardless of exactly when finish() runs relative to a racing
    enqueue()."""
    first_finished = threading.Event()
    hold = threading.Event()
    calls = []

    def fake_compute(destination_id):
        calls.append(destination_id)
        if len(calls) == 1:
            # Mimic compute_for_destination's real behavior: it marks the
            # run terminal itself, before ever returning to the worker --
            # then stay inside this call (as if still cleaning up) so
            # backfill_queue's worker hasn't yet reached the point where it
            # clears destination 1 from `_active`. This is the exact
            # vulnerable window the bug lived in: status already terminal,
            # but the destination conceptually still "in flight".
            backfill_status.finish(destination_id, "done")
            first_finished.set()
            hold.wait(timeout=2.0)

    monkeypatch.setattr(compute, "compute_for_destination", fake_compute)

    backfill_queue.enqueue(1, total=5)
    assert first_finished.wait(timeout=2.0)

    # Fire several enqueue() calls for the same destination_id from other
    # threads while destination 1 is in that window -- all of these should
    # collapse into a single pending rerun, never each start their own
    # independent duplicate run.
    threads = [threading.Thread(target=backfill_queue.enqueue, args=(1, 5)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    hold.set()
    backfill_queue.wait_until_idle()
    assert calls == [1, 1]


def test_worker_recovers_from_an_exception_while_sizing_a_rerun(monkeypatch):
    """Regression test (review finding on this PR): an earlier draft only
    wrapped the compute_for_destination call itself in try/except -- an
    exception from the surrounding bookkeeping (e.g. listings_store.list_
    listings() failing while sizing a rerun) propagated out of the worker
    thread uncaught, permanently leaking _inflight (wedging
    wait_until_idle() forever) and silently dropping the rerun. The whole
    per-iteration body is now wrapped, so the worker recovers and still
    processes whatever's queued behind the failure."""
    release = threading.Event()
    calls = []

    def fake_compute(destination_id):
        calls.append(destination_id)
        if len(calls) == 1:
            release.wait(timeout=2.0)

    monkeypatch.setattr(compute, "compute_for_destination", fake_compute)

    backfill_queue.enqueue(1, total=5)
    assert _wait_for(lambda: backfill_status.get(1)["status"] == "running")

    # Queue a rerun while destination 1's first call is still blocked, so
    # the eventual rerun goes through _process_one's "if rerun:" branch --
    # exactly where the vulnerable list_listings() call sits.
    backfill_queue.enqueue(1, total=5)

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(backfill_queue.listings_store, "list_listings", boom)

    # Destination 2, queued behind 1, must still run despite 1's rerun
    # blowing up while sizing itself.
    backfill_queue.enqueue(2, total=1)

    release.set()

    backfill_queue.wait_until_idle(timeout=2.0)
    assert calls == [1, 2]


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
