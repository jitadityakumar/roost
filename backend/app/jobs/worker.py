"""Worker pools for both job lanes.

HttpLaneWorkerPool: a small number of concurrent asyncio workers pull jobs
from the queue and run their (blocking) handler in a thread. Paced with a
shared minimum interval between job starts so a burst of submissions doesn't
fire many concurrent Rightmove requests at once.

LlmLaneWorkerPool: a single worker, strictly serial by design (see
CLAUDE.md) — each `claude -p` call already takes several seconds, which is
its own natural pacing, so there's no MIN_JOB_START_INTERVAL_SECONDS
equivalent. Deliberately duplicates HttpLaneWorkerPool's claim/heartbeat loop
structure rather than generalizing into a shared base class — minimizes the
diff against working code for a two-lane app; worth revisiting if a third
lane ever appears. Does not run its own reclaim loop:
queue.reclaim_stale_leases() has no lane filter, so HttpLaneWorkerPool's
existing reclaim loop already covers stale llm-lane leases too — a second
loop would just race the first one over the same UPDATE, harmlessly but
pointlessly.
"""
from __future__ import annotations

import asyncio
import logging

from app.jobs import queue
from app.jobs.handlers import HANDLERS
from app.jobs.llm_client import LlmCallError

logger = logging.getLogger("roost.worker")

HTTP_LANE_CONCURRENCY = 3
MIN_JOB_START_INTERVAL_SECONDS = 1.0
POLL_INTERVAL_SECONDS = 2.0
RECLAIM_INTERVAL_SECONDS = 30.0
ERROR_BACKOFF_SECONDS = 5.0
# Comfortably inside LEASE_SECONDS (120s) so a renewal always lands before
# the lease would otherwise expire, even accounting for scheduling jitter.
HEARTBEAT_INTERVAL_SECONDS = 30.0


class HttpLaneWorkerPool:
    def __init__(self):
        self._tasks: list[asyncio.Task] = []
        self._start_lock = asyncio.Lock()
        self._stopping = False

    async def _paced_claim(self) -> dict | None:
        async with self._start_lock:
            job = await asyncio.to_thread(queue.claim_next_job, "http")
            if job is not None:
                await asyncio.sleep(MIN_JOB_START_INTERVAL_SECONDS)
            return job

    async def _heartbeat_while_running(self, job_id: int):
        """Keep a long-running job's lease alive so `reclaim_stale_leases`
        doesn't mistake a slow-but-alive handler (e.g. downloading 20+ media
        files, each with its own 30s timeout) for a dead worker and hand the
        same job to a second worker mid-flight."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                await asyncio.to_thread(queue.renew_lease, job_id)
        except asyncio.CancelledError:
            pass

    async def _run_one_job(self, worker_id: int, job: dict) -> None:
        handler = HANDLERS.get(job["job_type"])
        if handler is None:
            # No handler will ever exist for this job_type without a code
            # change, so retrying can't succeed — fail permanently instead
            # of requeueing it to fail the same way two more times.
            await asyncio.to_thread(
                queue.fail_job, job["id"], f"no handler registered for job_type={job['job_type']}", True
            )
            return

        logger.info("worker %d running job %d (%s)", worker_id, job["id"], job["job_type"])
        heartbeat_task = asyncio.create_task(self._heartbeat_while_running(job["id"]))
        try:
            await asyncio.to_thread(handler, job)
            await asyncio.to_thread(queue.complete_job, job["id"])
        except Exception as e:
            logger.exception("job %d (%s) failed", job["id"], job["job_type"])
            await asyncio.to_thread(queue.fail_job, job["id"], str(e))
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _worker_loop(self, worker_id: int):
        # Broad except around the whole loop body (not just handler
        # execution): an unhandled exception from claiming/completing/
        # failing a job used to propagate out of the loop and silently kill
        # this worker task for the rest of the process's life, with no
        # restart and no visible error. A short backoff avoids spinning hot
        # if the failure is persistent (e.g. the DB file becomes
        # unwritable).
        while not self._stopping:
            try:
                job = await self._paced_claim()
                if job is None:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                await self._run_one_job(worker_id, job)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("worker %d loop iteration failed", worker_id)
                await asyncio.sleep(ERROR_BACKOFF_SECONDS)

    async def _reclaim_loop(self):
        while not self._stopping:
            await asyncio.sleep(RECLAIM_INTERVAL_SECONDS)
            try:
                reclaimed = await asyncio.to_thread(queue.reclaim_stale_leases)
                if reclaimed:
                    logger.warning("reclaimed %d stale job lease(s)", reclaimed)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("reclaim loop iteration failed")

    def start(self):
        self._stopping = False
        for i in range(HTTP_LANE_CONCURRENCY):
            self._tasks.append(asyncio.create_task(self._worker_loop(i)))
        self._tasks.append(asyncio.create_task(self._reclaim_loop()))

    async def stop(self):
        self._stopping = True
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []


LLM_LANE_CONCURRENCY = 1  # strictly serial by design — see CLAUDE.md


class LlmLaneWorkerPool:
    """Single-worker pool for lane='llm'. See module docstring for why this
    duplicates HttpLaneWorkerPool's structure instead of sharing a base
    class, and why it doesn't run its own reclaim loop."""

    def __init__(self):
        self._tasks: list[asyncio.Task] = []
        self._stopping = False

    async def _heartbeat_while_running(self, job_id: int):
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                await asyncio.to_thread(queue.renew_lease, job_id)
        except asyncio.CancelledError:
            pass

    async def _run_one_job(self, job: dict) -> None:
        handler = HANDLERS.get(job["job_type"])
        if handler is None:
            await asyncio.to_thread(
                queue.fail_job, job["id"], f"no handler registered for job_type={job['job_type']}", True
            )
            return

        logger.info("llm worker running job %d (%s)", job["id"], job["job_type"])
        heartbeat_task = asyncio.create_task(self._heartbeat_while_running(job["id"]))
        try:
            await asyncio.to_thread(handler, job)
            await asyncio.to_thread(queue.complete_job, job["id"])
        except LlmCallError as e:
            logger.exception("job %d (%s) failed", job["id"], job["job_type"])
            await asyncio.to_thread(queue.fail_job, job["id"], str(e), e.permanent)
        except Exception as e:
            logger.exception("job %d (%s) failed", job["id"], job["job_type"])
            await asyncio.to_thread(queue.fail_job, job["id"], str(e))
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _worker_loop(self):
        while not self._stopping:
            try:
                job = await asyncio.to_thread(queue.claim_next_job, "llm")
                if job is None:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                await self._run_one_job(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("llm worker loop iteration failed")
                await asyncio.sleep(ERROR_BACKOFF_SECONDS)

    def start(self):
        self._stopping = False
        self._tasks.append(asyncio.create_task(self._worker_loop()))

    async def stop(self):
        self._stopping = True
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
