"""Google Maps Routes API v2 client, WALK mode only. Mirrors the request
pattern from ~/github/rail-disruption-monitor/app/routes_api.py (plain
urllib POST, X-Goog-Api-Key / X-Goog-FieldMask headers) with the
transit-only pieces dropped -- see context.md's "Station walking distance"
section for the design.

Reuses that project's GOOGLE_MAPS_API_KEY (app/config.py, no in-repo
default). A per-station failure here is caught and logged by the caller,
not raised -- the rightmove_extract job must still succeed even if Maps is
unreachable or the key is unset.
"""
import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.config import GOOGLE_MAPS_API_KEY

logger = logging.getLogger(__name__)

_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
_FIELD_MASK = "routes.duration,routes.distanceMeters"
_TIMEOUT_SECONDS = 30


class WalkingApiError(Exception):
    pass


def _latlng(lat: float, lon: float) -> dict:
    return {"location": {"latLng": {"latitude": lat, "longitude": lon}}}


def compute_walk_distance(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> dict:
    """Returns {"distance_meters": int, "duration_seconds": int}. Raises
    WalkingApiError on any failure (missing key, network, no route)."""
    if not GOOGLE_MAPS_API_KEY:
        raise WalkingApiError("GOOGLE_MAPS_API_KEY is not set")

    body = {
        "origin": _latlng(origin_lat, origin_lon),
        "destination": _latlng(dest_lat, dest_lon),
        "travelMode": "WALK",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": _FIELD_MASK,
    }
    req = Request(_ENDPOINT, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            result = json.loads(resp.read())
    except (URLError, TimeoutError, ValueError) as e:
        raise WalkingApiError(f"Routes API request failed: {e}") from e

    routes = result.get("routes") or []
    if not routes:
        raise WalkingApiError("Routes API returned no route")

    route = routes[0]
    duration_raw = route.get("duration", "")
    distance_meters = route.get("distanceMeters")
    if distance_meters is None or not duration_raw:
        raise WalkingApiError(f"Routes API response missing duration/distance: {route!r}")

    try:
        # protobuf Duration strings allow fractional seconds (e.g. "3.5s"),
        # so parse as float before truncating to whole seconds -- a bare
        # int() would raise ValueError and violate this function's "never
        # raise anything but WalkingApiError" contract.
        duration_seconds = int(float(duration_raw.rstrip("s") or 0))
        distance_meters = int(distance_meters)
    except (TypeError, ValueError) as e:
        raise WalkingApiError(f"Routes API response has unparseable duration/distance: {route!r}") from e

    return {"distance_meters": distance_meters, "duration_seconds": duration_seconds}
