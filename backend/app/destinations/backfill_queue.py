"""Global single-worker FIFO queue for compute.compute_for_destination
backfills -- follow-up to issue #36. Before this module existed, every
create/edit spawned its own dedicated thread, so backfilling 3-4
destinations in quick succession (each looping every listing, minutes for
a realistic listing count) meant that many threads hitting
train-journey-planner's /api/journeys concurrently. That service caps
concurrency at MAX_CONCURRENT_DB_REQUESTS (default 4) and
destinations/client.py's own 503 retry is bounded (2 retries) -- under
sustained contention from several parallel backfills, retries could
exhaust and a listing that does have a route would silently get no stored
row, indistinguishable from a genuine "no route found". Routing every
backfill through one worker, processed strictly one destination at a
time, removes that contention entirely at the cost of a later
destination's backfill visibly waiting behind earlier ones -- an honest
queue instead of several progress bars quietly racing each other.

Per-destination dedup (a rerun queued behind an already in-flight backfill
for the *same* destination_id, so N rapid edits collapse into at most one
follow-up run once the current one finishes) is unchanged from the
pre-queue design -- it just now also has to account for a destination
sitting in the FIFO, not-yet-started, which backfill_status's new
'queued' state (distinct from 'running') makes visible to the admin page
too.
"""
from __future__ import annotations

import logging
import queue
import threading

from app.destinations import backfill_status, compute
from app.listings import store as listings_store

logger = logging.getLogger(__name__)

_queue: "queue.Queue[int]" = queue.Queue()

# Guards _pending_reruns and _inflight together -- both are only ever
# mutated from route-handler threads (enqueue) or the single worker thread
# (_worker_loop), never concurrently with themselves, so a plain lock is
# enough (same reasoning the old per-destination _pending_reruns_lock used).
_lock = threading.Lock()
_idle_cv = threading.Condition(_lock)
_pending_reruns: set[int] = set()
_inflight = 0

_worker_thread: threading.Thread | None = None


def enqueue(destination_id: int, total: int) -> None:
    """Request a backfill for destination_id. If one isn't already queued
    or running for this destination_id, it joins the global FIFO (marked
    'queued' in backfill_status immediately, so a client polling right
    after the request returns sees that, never a stale 'done'/'failed'
    from a previous run). If one already is, this doesn't queue a second
    run -- it just remembers to rerun once the current one finishes."""
    if backfill_status.start(destination_id, total):
        with _lock:
            global _inflight
            _inflight += 1
            _ensure_worker_started()
        _queue.put(destination_id)
        return

    with _lock:
        _pending_reruns.add(destination_id)


def _ensure_worker_started() -> None:
    # Called with _lock already held. A single persistent daemon thread,
    # started lazily on first use and left running (it blocks on
    # _queue.get() between backfills) rather than one thread per backfill.
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        _worker_thread.start()


def _worker_loop() -> None:
    while True:
        destination_id = _queue.get()
        backfill_status.mark_running(destination_id)
        try:
            compute.compute_for_destination(destination_id)
        except Exception:
            # compute_for_destination already records 'failed' in
            # backfill_status before re-raising -- this is just so a
            # failure doesn't kill the worker thread and silently stop
            # every subsequently-queued destination from ever running.
            logger.exception("compute_for_destination(%s) failed", destination_id)

        with _lock:
            rerun = destination_id in _pending_reruns
            if rerun:
                _pending_reruns.discard(destination_id)

        if rerun:
            # Same conceptual unit of work continuing, not a new one --
            # deliberately doesn't touch _inflight here (see enqueue()).
            total = len(listings_store.list_listings())
            backfill_status.start(destination_id, total)
            _queue.put(destination_id)
        else:
            with _lock:
                global _inflight
                _inflight -= 1
                if _inflight == 0:
                    _idle_cv.notify_all()


def wait_until_idle(timeout: float = 10.0) -> None:
    """Test-only: block until every queued/running/rerun-pending backfill
    has finished. conftest.py's isolated_db fixture calls this at teardown
    so a backfill still in flight from one test can never run against the
    next test's freshly repointed (and not-yet-migrated) ROOST_DB_PATH --
    same purpose the old per-thread join served before this module
    existed, just against the shared queue/worker instead of a list of
    one-off threads."""
    with _idle_cv:
        _idle_cv.wait_for(lambda: _inflight == 0, timeout=timeout)
