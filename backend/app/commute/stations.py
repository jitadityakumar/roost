"""Static name -> CRS code resolution for Rightmove's `nearest_stations_raw`
station list, against a copied `stations.csv` (National Rail only -- see
README.md for the dataset's ODbL attribution).

No network call and nothing to cache: cheap enough to redo on every listing-
detail page load. See context.md's "Phase 2: commute-station join" for the
design and the suffix-stripping validation against real listing data.
"""
import csv
import os
import re

STATIONS_CSV = os.path.join(os.path.dirname(__file__), "stations.csv")

MAX_DISTANCE_MILES = 0.5

_SUFFIX_RE = re.compile(r"\s+(Station|Tram Stop)$")


def _load_name_to_crs() -> dict[str, str]:
    with open(STATIONS_CSV, newline="", encoding="utf-8") as f:
        return {row["stationName"]: row["crsCode"] for row in csv.DictReader(f)}


_NAME_TO_CRS = _load_name_to_crs()


def strip_station_suffix(name: str) -> str:
    return _SUFFIX_RE.sub("", name)


def resolve_crs_codes(nearest_stations_raw: list[dict]) -> list[dict]:
    """Filter to National Rail entries, strip the Rightmove suffix, and
    resolve each to a CRS code. Tube/tram-only stations (absent from
    `stations.csv` by design) and any other unresolvable name are dropped
    rather than erroring -- see context.md, 3/20 misses validated as
    tube/tram-only. Dedupes by CRS code (equidistant Rightmove entries can
    resolve to the same station).

    Only stations within `MAX_DISTANCE_MILES` are returned, since a commute
    from further away isn't realistically walkable. A station with no
    distance is dropped by this filter (nothing to compare against), but
    not from resolution otherwise -- if none of the resolved stations have
    a distance at all, the filter is skipped and everything resolved is
    returned rather than silently producing an empty list."""
    resolved = []
    seen_crs = set()
    for entry in nearest_stations_raw:
        if "NATIONAL_TRAIN" not in (entry.get("types") or []):
            continue
        name = strip_station_suffix(entry.get("name", ""))
        crs = _NAME_TO_CRS.get(name)
        if not crs or crs in seen_crs:
            continue
        seen_crs.add(crs)
        resolved.append({"name": name, "crs": crs, "distance": entry.get("distance")})

    if not any(r["distance"] is not None for r in resolved):
        return resolved
    return [r for r in resolved if r["distance"] is not None and r["distance"] <= MAX_DISTANCE_MILES]
