"""Global single-worker FIFO queue for compute.compute_for_destination
backfills -- follow-up to issue #36. Before this module existed, every
create/edit spawned its own dedicated thread, so backfilling 3-4
destinations in quick succession (each looping every listing) meant that
many threads hitting TfL's Journey Planner API concurrently -- routing
every backfill through one worker, processed strictly one destination at a
time, keeps every caller of app.commute.tfl_client under its single shared
throttle regardless of how many destinations are backfilling, at the cost
of a later destination's backfill visibly waiting behind earlier ones -- an
honest queue instead of several progress bars quietly racing each other.
(Originally written against train-journey-planner, which had its own
concurrency cap and bounded 503 retry this queue existed to protect --
issue #47 replaced that service with TfL entirely, but the queue's
one-at-a-time discipline is still the right shape now that
tfl_client.py's module-level throttle is the thing every caller shares.)

Per-destination dedup (a rerun queued behind an already in-flight backfill
for the *same* destination_id, so N rapid edits collapse into at most one
follow-up run once the current one finishes) is unchanged in spirit from
the pre-queue design, but **this module -- not backfill_status -- is the
sole authority on "is a backfill for this destination_id already
queued/running"**, via the process-local `_active` set. This was a real
bug in an earlier draft (caught in review): compute_for_destination calls
backfill_status.finish() to mark a run terminal *before* control returns
here, so gating on backfill_status's own state left a window where a
fresh enqueue() arriving right after finish() (but before this module
noticed a pending rerun) would see "not active" and start a second,
fully independent run for the same destination_id at the same time as
the queued rerun -- duplicating that destination's whole-listing backfill
instead of collapsing to one. `_active` is mutated only under `_lock`, by
this module alone, so there's no such window.
"""
from __future__ import annotations

import logging
import queue
import threading

from app.destinations import backfill_status, compute
from app.listings import store as listings_store

logger = logging.getLogger(__name__)

_queue: "queue.Queue[int]" = queue.Queue()

# All mutated together, only ever under _lock, only from route-handler
# threads (enqueue) or the single worker thread (_worker_loop/_process_one)
# -- never concurrently with themselves, so a plain lock is enough.
_lock = threading.Lock()
_idle_cv = threading.Condition(_lock)
_active: set[int] = set()  # destination_ids currently queued or running
_pending_reruns: set[int] = set()
_inflight = 0  # number of destination_ids with outstanding work (== len(_active) at rest)

_worker_thread: threading.Thread | None = None


def enqueue(destination_id: int, total: int) -> None:
    """Request a backfill for destination_id. If one isn't already queued
    or running for this destination_id (per `_active`, not backfill_status
    -- see module docstring), it joins the global FIFO and is marked
    'queued' in backfill_status immediately, so a client polling right
    after the request returns sees that, never a stale 'done'/'failed'
    from a previous run. If one already is, this doesn't queue a second
    run -- it just remembers to rerun once the current one finishes."""
    with _lock:
        global _inflight
        if destination_id in _active:
            _pending_reruns.add(destination_id)
            return
        _active.add(destination_id)
        _inflight += 1
        _ensure_worker_started()
    # Reserving destination_id in `_active` above (under the same lock)
    # guarantees no concurrent enqueue() call for this same destination_id
    # can reach here too -- safe to touch backfill_status/the queue outside
    # the lock.
    backfill_status.start(destination_id, total)
    _queue.put(destination_id)


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
        try:
            _process_one(destination_id)
        except Exception:
            # Whatever went wrong (compute_for_destination itself already
            # catches its own errors -- this is the surrounding bookkeeping,
            # e.g. listings_store.list_listings() failing while sizing a
            # rerun), the worker thread must survive so every
            # subsequently-queued destination still gets processed, and
            # this destination_id's state must not be left dangling (stuck
            # 'active' forever, or _inflight leaked so wait_until_idle()
            # never returns).
            logger.exception("backfill_queue worker failed processing destination %s", destination_id)
            with _lock:
                global _inflight
                _active.discard(destination_id)
                _pending_reruns.discard(destination_id)
                _inflight -= 1
                if _inflight == 0:
                    _idle_cv.notify_all()


def _process_one(destination_id: int) -> None:
    backfill_status.mark_running(destination_id)
    try:
        compute.compute_for_destination(destination_id)
    except Exception:
        # compute_for_destination already records 'failed' in
        # backfill_status before re-raising -- this is just so a failure
        # doesn't propagate out of _process_one (that's reserved for
        # bookkeeping failures the outer _worker_loop needs to clean up
        # after, see there).
        logger.exception("compute_for_destination(%s) failed", destination_id)

    with _lock:
        global _inflight
        rerun = destination_id in _pending_reruns
        if rerun:
            _pending_reruns.discard(destination_id)
        else:
            _active.discard(destination_id)
            _inflight -= 1
            if _inflight == 0:
                _idle_cv.notify_all()

    if rerun:
        # Same conceptual unit of work continuing (destination_id stays in
        # `_active`, _inflight untouched above) -- if anything below raises,
        # _worker_loop's except clause still cleans up `_active`/_inflight
        # correctly.
        total = len(listings_store.list_listings())
        backfill_status.start(destination_id, total)
        _queue.put(destination_id)


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
