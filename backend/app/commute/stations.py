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

MAX_DISTANCE_MILES = 1.0

_SUFFIX_RE = re.compile(r"\s+(Station|Tram Stop)$")

# Strip periods and both straight/curly apostrophes, lowercase, collapse
# whitespace -- but never touch spaces themselves. Rightmove sends names
# like "St. Helier Station" while stations.csv has "St Helier" (validated:
# zero periods anywhere in stations.csv); collapsing whitespace too would
# be unsafe -- "How Wood" (CRS HWW) and "Howwood" (CRS HOZ) are genuinely
# different stations that would collide if spaces were stripped.
_PUNCT_RE = re.compile(r"[.’']")


def _normalize_name(name: str) -> str:
    name = _PUNCT_RE.sub("", name)
    return re.sub(r"\s+", " ", name).strip().lower()


def _load_name_to_crs() -> dict[str, str]:
    with open(STATIONS_CSV, newline="", encoding="utf-8") as f:
        return {_normalize_name(row["stationName"]): row["crsCode"] for row in csv.DictReader(f)}


def _load_crs_to_latlong() -> dict[str, tuple[float, float]]:
    with open(STATIONS_CSV, newline="", encoding="utf-8") as f:
        return {row["crsCode"]: (float(row["lat"]), float(row["long"])) for row in csv.DictReader(f)}


_NAME_TO_CRS = _load_name_to_crs()
_CRS_TO_LATLONG = _load_crs_to_latlong()


def latlong_for_crs(crs: str) -> tuple[float, float] | None:
    return _CRS_TO_LATLONG.get(crs)


def strip_station_suffix(name: str) -> str:
    return _SUFFIX_RE.sub("", name)


def resolve_crs_codes(nearest_stations_raw: list[dict]) -> list[dict]:
    """Filter to National Rail entries, strip the Rightmove suffix, and
    resolve each to a CRS code. Tube/tram-only stations (absent from
    `stations.csv` by design) and any other unresolvable name are dropped
    rather than erroring -- see context.md, 3/20 misses validated as
    tube/tram-only. Dedupes by CRS code (equidistant Rightmove entries can
    resolve to the same station).

    Only stations within `MAX_DISTANCE_MILES` are returned -- this is the
    candidate set for the Commute section (routes/commute.py), which is
    national-rail-only regardless of issue #40 PR2's walking-distance scope
    expansion (station_walk_distances now covers every mode/distance, see
    app/jobs/handlers.py -- this function's job is unchanged, it's just no
    longer that computation's own candidate set).

    Each result carries "index" -- the entry's position in the original
    nearest_stations_raw list -- so callers can look up station_walk_distances
    (keyed by that same index, see walk_store.py) without re-deriving a CRS
    lookup of their own. A station with no distance is dropped by the
    MAX_DISTANCE_MILES filter (nothing to compare against), but not from
    resolution otherwise -- if none of the resolved stations have a distance
    at all, the filter is skipped and everything resolved is returned rather
    than silently producing an empty list."""
    resolved = []
    seen_crs = set()
    for index, entry in enumerate(nearest_stations_raw):
        if "NATIONAL_TRAIN" not in (entry.get("types") or []):
            continue
        name = strip_station_suffix(entry.get("name", ""))
        crs = _NAME_TO_CRS.get(_normalize_name(name))
        if not crs or crs in seen_crs:
            continue
        seen_crs.add(crs)
        resolved.append({"name": name, "crs": crs, "distance": entry.get("distance"), "index": index})

    if not any(r["distance"] is not None for r in resolved):
        return resolved
    return [r for r in resolved if r["distance"] is not None and r["distance"] <= MAX_DISTANCE_MILES]
