"""Thin client for postcodes.io (geocoding) + data.police.uk (crime data),
ported from the standalone crime-rate-tracker script. Both are fixed public
APIs (not deployer-configured like commute/mortgage's sibling services), and
a postcode only ever feeds a query param here, never a URL -- no SSRF
concern, same reasoning as app/commute/client.py.

data.police.uk's crimes-street endpoint only accepts one month per request
(no date-range param), so a full 12-month fetch means 12 calls; the API
allows 15 req/s sustained / burst 30 and returns HTTP 429 if exceeded (see
https://data.police.uk/docs/api-call-limits/), so every call here is
throttled with a fixed delay plus exponential backoff on 429.
"""
import json
import time
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from app.crime.store import normalize_postcode

POSTCODES_IO = "https://api.postcodes.io/postcodes/{}"
POLICE_DATES = "https://data.police.uk/api/crimes-street-dates"
POLICE_CRIMES = "https://data.police.uk/api/crimes-street/all-crime"

REQUEST_DELAY_SECONDS = 0.15
REQUEST_TIMEOUT_SECONDS = 15
MAX_RETRIES = 5


class CrimeApiError(Exception):
    pass


def _throttled_get(url: str, params: dict | None = None) -> dict | list:
    full_url = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    for attempt in range(MAX_RETRIES):
        try:
            with urlopen(full_url, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            time.sleep(REQUEST_DELAY_SECONDS)
            return data
        except HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
                continue
            raise CrimeApiError(f"request failed for {full_url}: {e}") from e
        except (URLError, TimeoutError, ValueError) as e:
            raise CrimeApiError(f"request failed for {full_url}: {e}") from e
    raise CrimeApiError(f"gave up after {MAX_RETRIES} retries: {full_url}")


def geocode_postcode(postcode: str) -> tuple[float, float]:
    data = _throttled_get(POSTCODES_IO.format(urllib.parse.quote(normalize_postcode(postcode))))
    result = data.get("result")
    if not result:
        raise CrimeApiError(f"postcode not found: {postcode!r}")
    return result["latitude"], result["longitude"]


def last_12_months() -> list[str]:
    dates = _throttled_get(POLICE_DATES)
    return sorted((d["date"] for d in dates), reverse=True)[:12]


def fetch_crimes(lat: float, lng: float, month: str) -> list[dict]:
    return _throttled_get(POLICE_CRIMES, params={"lat": lat, "lng": lng, "date": month})


def fetch_category_counts(lat: float, lng: float) -> dict[str, int]:
    """Sums crime counts per category over the last 12 available months."""
    counts: dict[str, int] = {}
    for month in last_12_months():
        for crime in fetch_crimes(lat, lng, month):
            category = crime["category"]
            counts[category] = counts.get(category, 0) + 1
    return counts
