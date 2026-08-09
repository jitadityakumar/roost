"""Thin client for london-commuter-stations' station-lookup API. Deployers
set its address via ROOST_COMMUTE_API_BASE (no in-repo default -- see
app/config.py); if it's a separate host reached over Tailscale from inside
Roost's Docker container, a host-level firewall rule may be needed to let
the container's bridge subnet through (not tracked in this repo).

No SSRF concern here (unlike Rightmove URL handling in url_utils.py): the
host/port comes from deployer-controlled config, never from user input.
"""
import json
from urllib.error import URLError
from urllib.request import urlopen

from app.config import COMMUTE_API_BASE

TIMEOUT_SECONDS = 5


class CommuteApiError(Exception):
    pass


def fetch_station_termini(crs: str) -> dict:
    if not COMMUTE_API_BASE:
        raise CommuteApiError(
            "ROOST_COMMUTE_API_BASE is not set -- the commute API's address "
            "must be configured via environment variable, see CLAUDE.md"
        )
    url = f"{COMMUTE_API_BASE}/api/station/{crs}?time=both"
    try:
        with urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError) as e:
        raise CommuteApiError(f"commute API request failed for {crs}: {e}") from e
