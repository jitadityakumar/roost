"""Thin client for train-journey-planner's /api/journeys endpoint. Mirrors
app/commute/client.py's pattern (plain urllib GET, no in-repo default for
the base URL -- see app/config.py) -- train-journey-planner runs on the
same Tailscale-only host as london-commuter-stations/mortgage-calculator.

train-journey-planner's own CLAUDE.md documents /api/journeys as one of a
handful of DB-touching routes bounded by MAX_CONCURRENT_DB_REQUESTS
(default 4 concurrent requests, per that app's own load testing): a
request that can't get a slot within DB_REQUEST_ACQUIRE_TIMEOUT_SECONDS
(default 5s) gets a 503 with a Retry-After header rather than queueing
indefinitely. Roost only ever issues one train-journey-planner request at
a time itself (compute.py's per-origin loop is sequential, and so is
compute_for_destination's per-listing loop), so it can never be the cause
of hitting that cap -- but the service can still be busy with other
traffic (a human using its own web form, or an unrelated app). A 503 here
must be retried per that documented contract, not treated the same as a
genuine "no route" -- see _fetch_with_retry below.

Also wraps /api/journeys/multi-change, train-journey-planner's separate
2-5 change fallback tier (its own issue #26) backed by an OpenTripPlanner
sidecar rather than that app's own SQLite index. train-journey-planner's
CLAUDE.md documents this as a strict second stage: call /api/journeys
first, and only call /api/journeys/multi-change if that came back with
zero journeys -- compute.py follows exactly that pattern per origin, per
train-journey-planner's own reference implementation
(app/static/multi_change.js there). Unlike /api/journeys, this endpoint
never 503s (it's deliberately excluded from MAX_CONCURRENT_DB_REQUESTS and
has its own separate OTP_MAX_CONCURRENT_SIDECAR_REQUESTS budget instead,
which degrades rather than queues) and never hard-fails -- a down/unhealthy
sidecar still returns 200 with sidecar_healthy: false and journeys: [], so
fetch_multi_change_journeys has no retry loop, only the same network/parse
error handling as fetch_journeys.
"""
import datetime as dt
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.config import TRAIN_PLANNER_BASE

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
WINDOW_MINUTES = 60

# Bounds how long a single fetch_journeys call will wait out 503s before
# giving up -- train-journey-planner's own acquire timeout defaults to 5s,
# so two retries covers one real transient busy period without letting a
# sustained outage stall Roost's (already unbounded-length, see PR review)
# synchronous backfill loop indefinitely.
MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 10


class TrainPlannerApiError(Exception):
    pass


def _fetch_with_retry(url: str) -> dict:
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code != 503 or attempt == MAX_RETRIES:
                raise
            retry_after = min(int(e.headers.get("Retry-After", 5)), MAX_RETRY_AFTER_SECONDS)
            logger.info(
                "train-journey-planner at capacity (503), retrying in %ss (attempt %d/%d)",
                retry_after,
                attempt + 1,
                MAX_RETRIES,
            )
            time.sleep(retry_after)
    raise AssertionError("unreachable")  # loop always returns or raises


def fetch_journeys(from_crs: str, to_crs: str, date: dt.date, time_: dt.time) -> dict:
    """Returns train-journey-planner's JourneysResponse dict. Raises
    TrainPlannerApiError on any failure (base URL unset, network, non-200
    after retries, unparseable body) -- the caller (compute.py) treats a
    failed origin as just not contributing a candidate, same as
    tfl_client.py's per-station failure handling."""
    if not TRAIN_PLANNER_BASE:
        raise TrainPlannerApiError(
            "ROOST_TRAIN_PLANNER_BASE is not set -- the train-journey-planner API's "
            "address must be configured via environment variable, see CLAUDE.md"
        )
    params = {
        "from": from_crs,
        "to": to_crs,
        "date": date.isoformat(),
        "time": time_.strftime("%H:%M"),
        "window_minutes": WINDOW_MINUTES,
    }
    url = f"{TRAIN_PLANNER_BASE}/api/journeys?{urlencode(params)}"
    try:
        return _fetch_with_retry(url)
    except (URLError, TimeoutError, ValueError) as e:
        raise TrainPlannerApiError(f"train-journey-planner request failed for {from_crs}->{to_crs}: {e}") from e


def fetch_multi_change_journeys(from_crs: str, to_crs: str, date: dt.date, time_: dt.time) -> dict:
    """Returns train-journey-planner's MultiChangeJourneysResponse dict.
    Raises TrainPlannerApiError on any failure (base URL unset, network,
    non-200, unparseable body) -- same caller contract as fetch_journeys.
    Only ever meaningful as a second-stage call after fetch_journeys came
    back with zero journeys -- see module docstring."""
    if not TRAIN_PLANNER_BASE:
        raise TrainPlannerApiError(
            "ROOST_TRAIN_PLANNER_BASE is not set -- the train-journey-planner API's "
            "address must be configured via environment variable, see CLAUDE.md"
        )
    params = {
        "from": from_crs,
        "to": to_crs,
        "date": date.isoformat(),
        "time": time_.strftime("%H:%M"),
        "window_minutes": WINDOW_MINUTES,
    }
    url = f"{TRAIN_PLANNER_BASE}/api/journeys/multi-change?{urlencode(params)}"
    try:
        with urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as e:
        raise TrainPlannerApiError(f"train-journey-planner multi-change request failed for {from_crs}->{to_crs}: {e}") from e


def results_url(from_crs: str, to_crs: str, date: dt.date, time: dt.time) -> str | None:
    """Deep link to train-journey-planner's own human-facing /results page
    for this exact query -- lets the user see the full live result set
    train-journey-planner found, not just the single best pick Roost
    stored. Free (no extra API call), same "link to the source app"
    convention as the existing Rightmove/Google Maps links. None if the
    base URL isn't configured."""
    if not TRAIN_PLANNER_BASE:
        return None
    params = {
        "from_": from_crs,
        "to": to_crs,
        "date": date.isoformat(),
        "time": time.strftime("%H:%M"),
        "window_minutes": WINDOW_MINUTES,
    }
    return f"{TRAIN_PLANNER_BASE}/results?{urlencode(params)}"
