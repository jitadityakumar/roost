"""Thin client for train-journey-planner's /api/journeys endpoint. Mirrors
app/commute/client.py's pattern (plain urllib GET, no in-repo default for
the base URL -- see app/config.py) -- train-journey-planner runs on the
same Tailscale-only host as london-commuter-stations/mortgage-calculator.
"""
import datetime as dt
import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.config import TRAIN_PLANNER_BASE

TIMEOUT_SECONDS = 10
WINDOW_MINUTES = 60


class TrainPlannerApiError(Exception):
    pass


def fetch_journeys(from_crs: str, to_crs: str, date: dt.date, time: dt.time) -> dict:
    """Returns train-journey-planner's JourneysResponse dict. Raises
    TrainPlannerApiError on any failure (base URL unset, network, non-200,
    unparseable body) -- the caller (compute.py) treats a failed origin as
    just not contributing a candidate, same as walking.py's per-station
    failure handling."""
    if not TRAIN_PLANNER_BASE:
        raise TrainPlannerApiError(
            "ROOST_TRAIN_PLANNER_BASE is not set -- the train-journey-planner API's "
            "address must be configured via environment variable, see CLAUDE.md"
        )
    params = {
        "from": from_crs,
        "to": to_crs,
        "date": date.isoformat(),
        "time": time.strftime("%H:%M"),
        "window_minutes": WINDOW_MINUTES,
    }
    url = f"{TRAIN_PLANNER_BASE}/api/journeys?{urlencode(params)}"
    try:
        with urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError) as e:
        raise TrainPlannerApiError(f"train-journey-planner request failed for {from_crs}->{to_crs}: {e}") from e


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
