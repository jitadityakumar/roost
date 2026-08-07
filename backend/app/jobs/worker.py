"""Minimal lane='http' worker pool: a small number of concurrent asyncio
workers pull jobs from the queue and run their (blocking) handler in a
thread. Paced with a shared minimum interval between job starts so a burst
of submissions doesn't fire many concurrent Rightmove requests at once.

lane='llm' has no workers here — Phase 1 never enqueues llm-lane jobs at all
(no LLM enrichment worker exists yet, see context.md decision log).
"""
from __future__ import annotations

import asyncio
import logging

from app.jobs import queue
from app.jobs.handlers import HANDLERS

logger = logging.getLogger("roost.worker")

HTTP_LANE_CONCURRENCY = 3
MIN_JOB_START_INTERVAL_SECONDS = 1.0
POLL_INTERVAL_SECONDS = 2.0
RECLAIM_INTERVAL_SECONDS = 30.0


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

    async def _worker_loop(self, worker_id: int):
        while not self._stopping:
            job = await self._paced_claim()
            if job is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            handler = HANDLERS.get(job["job_type"])
            if handler is None:
                queue.fail_job(job["id"], f"no handler registered for job_type={job['job_type']}")
                continue

            logger.info("worker %d running job %d (%s)", worker_id, job["id"], job["job_type"])
            try:
                await asyncio.to_thread(handler, job)
                queue.complete_job(job["id"])
            except Exception as e:
                logger.exception("job %d (%s) failed", job["id"], job["job_type"])
                queue.fail_job(job["id"], str(e))

    async def _reclaim_loop(self):
        while not self._stopping:
            await asyncio.sleep(RECLAIM_INTERVAL_SECONDS)
            reclaimed = await asyncio.to_thread(queue.reclaim_stale_leases)
            if reclaimed:
                logger.warning("reclaimed %d stale job lease(s)", reclaimed)

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
