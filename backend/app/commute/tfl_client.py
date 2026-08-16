"""TfL Unified API (api.tfl.gov.uk) client -- station-name resolution +
real routed walking distance/duration, replacing Google Routes API v2
(formerly app/commute/walking.py, deleted). Free (500 req/min with a
registered key vs. Google's billed-per-call Routes API) -- see issue #40's
plan comment for the full validation writeup this implementation follows.

Station resolution is the hard part: TfL keys stations by StopPoint id, not
CRS code, and free-text search against `/StopPoint/Search` can return a
nearby but wrong station (e.g. Rightmove's "Streatham Station" resolving to
the physically-closer-but-wrong "Streatham Common"). Validated fix (171/171
correct against Roost's real listing data): score each candidate by how
close its haversine distance from the listing is to Rightmove's own stated
straight-line distance, not by raw closeness -- see resolve_stop_point.
"""
import json
import logging
import re
import threading
import time
from collections import deque
from math import asin, cos, radians, sin, sqrt
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import TFL_API_KEY

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10

# api.tfl.gov.uk sits behind Cloudflare, which 403s (error code 1010) on
# urllib's default User-Agent -- any non-default string works, found live
# during issue #40's validation.
_HEADERS = {"User-Agent": "Roost/1.0 (+https://github.com/jitadityakumar/roost)"}

# TfL's registered-key cap is 500 req/min. Stay well under it (not the full
# 500) so every caller of this module -- a bulk backfill looping over many
# listings as well as a single manual "recompute" refresh -- is protected
# automatically, with headroom for jitter/latency. Module-level (not per
# caller) so it holds regardless of what's calling in.
_MAX_CALLS_PER_MINUTE = 400
_RATE_WINDOW_SECONDS = 60
_call_times: deque[float] = deque()
# HttpLaneWorkerPool runs job handlers on real OS threads (asyncio.to_thread),
# not coroutines -- the evict/check/sleep/append sequence below isn't atomic
# without a lock, so concurrent callers could both pass the check and briefly
# push the actual rate over _MAX_CALLS_PER_MINUTE.
_throttle_lock = threading.Lock()


def _throttle(now: float | None = None) -> None:
    with _throttle_lock:
        now = time.monotonic() if now is None else now
        while _call_times and now - _call_times[0] > _RATE_WINDOW_SECONDS:
            _call_times.popleft()
        if len(_call_times) >= _MAX_CALLS_PER_MINUTE:
            sleep_for = _RATE_WINDOW_SECONDS - (now - _call_times[0])
            if sleep_for > 0:
                logger.info(
                    "TfL API throttle: sleeping %.1fs to stay under %d req/min", sleep_for, _MAX_CALLS_PER_MINUTE
                )
                time.sleep(sleep_for)
        _call_times.append(time.monotonic())


class TflApiError(Exception):
    pass


def _append_key(url: str) -> str:
    if not TFL_API_KEY:
        raise TflApiError("TFL_API_KEY is not set")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}app_key={TFL_API_KEY}"


def _get(url: str) -> dict | list:
    _throttle()
    req = Request(_append_key(url), headers=_HEADERS)
    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, ValueError) as e:
        raise TflApiError(f"TfL API request failed: {e}") from e


# Rightmove sends fuller suffixes than stations.strip_station_suffix
# handles (that function only strips the bare "Station"/"Tram Stop" word --
# see stations.py:17 -- it's still used unchanged for stations.csv/CRS
# lookups and must not be widened). This tolerates either the bare or the
# fuller "<Mode> Station" form, since which one survives affects what's sent
# to TfL's search endpoint.
_SUFFIX_RE = re.compile(r"\s+(Rail Station|Underground Station|DLR Station|Overground Station|Tram Stop|Station)$")


def _strip_suffix(name: str) -> str:
    return _SUFFIX_RE.sub("", name)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_miles = 3958.8
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * earth_radius_miles * asin(sqrt(a))


def resolve_stop_point(
    name: str,
    mode: str,
    listing_lat: float,
    listing_lon: float,
    rightmove_distance_miles: float | None,
    search_modes: str | None = None,
) -> str | None:
    """Resolve a Rightmove station name to a TfL StopPoint id, or None if it
    can't be resolved (never raises -- a station TfL can't resolve
    shouldn't fail the whole scrape job).

    Scores each `/StopPoint/Search` candidate by
    abs(haversine(listing, candidate) - rightmove_distance_miles) and picks
    the smallest gap, rather than the outright-closest candidate -- plain
    closest-lat/lon mis-resolved two real stations in validation (see module
    docstring). Falls back to plain closest-lat/lon if
    rightmove_distance_miles is None (Rightmove sometimes omits `distance`)
    or isn't in miles (Rightmove's `unit` field defaults to miles but isn't
    guaranteed to be; gap-scoring against a non-mile value would silently
    mis-rank candidates).

    `search_modes` (comma-joined, e.g. "national-rail,elizabeth-line")
    widens the `/StopPoint/Search` query beyond the single canonical `mode`
    -- TfL's own StopPoint data classifies some Rightmove-NATIONAL_TRAIN
    stations (e.g. Chadwell Heath, Goodmayes) as elizabeth-line-only, not
    national-rail, so a strict single-mode search misses them entirely.
    Defaults to `mode` when omitted. Deliberately NOT implemented as "search
    all modes, drop bus stops" -- validated against Roost's real listing
    data (issue #40 follow-up) and that broader search picked a wrong
    station (Putney Pier, modes=["bus","river-bus"], over the real Putney
    Rail Station) because river-bus/coach/etc aren't bus and can still
    outscore the correct station on the gap heuristic. An explicit allowlist
    per Rightmove type is the only safe way to widen this."""
    query = _strip_suffix(name.strip())
    if not query:
        return None
    try:
        data = _get(f"https://api.tfl.gov.uk/StopPoint/Search/{quote(query)}?modes={search_modes or mode}")
    except TflApiError as e:
        logger.info("TfL StopPoint/Search failed for %r: %s", name, e)
        return None

    matches = data.get("matches") or [] if isinstance(data, dict) else []
    # Also requires "id" -- an unexpected TfL response shape (missing id on
    # a match) must degrade to "unresolvable," not raise, per this
    # function's never-raise contract.
    candidates = [m for m in matches if m.get("lat") is not None and m.get("lon") is not None and m.get("id")]
    if not candidates:
        return None

    def gap(m: dict) -> float:
        return abs(_haversine_miles(listing_lat, listing_lon, m["lat"], m["lon"]) - rightmove_distance_miles)

    def closeness(m: dict) -> float:
        return _haversine_miles(listing_lat, listing_lon, m["lat"], m["lon"])

    try:
        if rightmove_distance_miles is not None:
            best = min(candidates, key=gap)
        else:
            best = min(candidates, key=closeness)
        stop_id = best["id"]
    except (KeyError, TypeError, ValueError):
        logger.info("TfL StopPoint/Search returned unparseable candidates for %r", name)
        return None

    if stop_id.startswith("HUB"):
        return _resolve_hub_child(stop_id, mode, listing_lat, listing_lon)
    return stop_id


def _resolve_hub_child(hub_id: str, mode: str, listing_lat: float, listing_lon: float) -> str | None:
    """A HUB id groups several StopPoints of different modes at one
    multi-modal interchange (e.g. HUBSRA for Stratford) -- drill into its
    children for the one matching the target mode."""
    try:
        data = _get(f"https://api.tfl.gov.uk/StopPoint/{hub_id}")
    except TflApiError as e:
        logger.info("TfL StopPoint/%s hub lookup failed: %s", hub_id, e)
        return None
    if not isinstance(data, dict):
        return None

    children = data.get("children") or []
    matching = [c for c in children if mode in (c.get("modes") or []) and c.get("id")]
    if not matching:
        return None
    if len(matching) == 1:
        return matching[0]["id"]

    # Not yet confirmed what the right tiebreak is here -- hasn't come up in
    # testing. Fall back to closest-lat/lon and log it as worth a second
    # look, per issue #40's plan.
    logger.warning("TfL hub %s has multiple '%s' children: %s", hub_id, mode, [c.get("id") for c in matching])
    with_latlon = [c for c in matching if c.get("lat") is not None and c.get("lon") is not None]
    if not with_latlon:
        return matching[0]["id"]
    try:
        closest = min(with_latlon, key=lambda c: _haversine_miles(listing_lat, listing_lon, c["lat"], c["lon"]))
        return closest["id"]
    except (KeyError, TypeError, ValueError):
        return matching[0]["id"]


def compute_walk_distance(origin_lat: float, origin_lon: float, stop_point_id: str) -> dict:
    """Returns {"distance_meters": int | None, "duration_seconds": int}.
    Raises TflApiError on any failure (missing key, network, no journey, no
    duration). distance_meters is only ever None if TfL's leg genuinely
    omits it while still returning a duration -- not yet observed live, but
    the frontend already requires both fields non-null to render a walk
    figure, so this degrades to "no walk figure shown" rather than an
    error."""
    origin = f"{origin_lat},{origin_lon}"
    url = f"https://api.tfl.gov.uk/Journey/JourneyResults/{quote(origin)}/to/{quote(stop_point_id)}?mode=walking"
    data = _get(url)

    if not isinstance(data, dict) or "journeys" not in data:
        # A 300 (ambiguous from/to) or other unexpected shape won't raise
        # via urlopen -- guard explicitly rather than crash on a missing key.
        raise TflApiError(f"TfL Journey API response missing journeys: {data!r}")

    journeys = data.get("journeys") or []
    if not journeys:
        raise TflApiError("TfL Journey API returned no journeys")

    legs = journeys[0].get("legs") or []
    if not legs:
        raise TflApiError(f"TfL Journey API journey has no legs: {journeys[0]!r}")

    leg = legs[0]
    duration_raw = leg.get("duration")
    distance_raw = leg.get("distance")
    if duration_raw is None:
        raise TflApiError(f"TfL Journey API leg missing duration: {leg!r}")

    try:
        duration_seconds = int(round(float(duration_raw) * 60))
        distance_meters = int(round(float(distance_raw))) if distance_raw is not None else None
    except (TypeError, ValueError) as e:
        raise TflApiError(f"TfL Journey API leg has unparseable duration/distance: {leg!r}") from e

    return {"distance_meters": distance_meters, "duration_seconds": duration_seconds}
