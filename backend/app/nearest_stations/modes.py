"""TfL mode -> Rightmove `types` translation, so nearest_station_candidates
rows (TfL-sourced) can reuse the frontend's existing Rightmove-type-keyed
badge/logo lookups (NearestStations.jsx's TYPE_BADGES, networkLogos.js's
LOGO_FILES) without either needing to change. Same mapping as
JourneyDetailsPage.jsx's LEG_BADGES on the frontend -- kept here rather than
duplicated because this translation now needs to happen at the API boundary,
not just for display.
"""
from __future__ import annotations

_MODE_TO_RIGHTMOVE_TYPE = {
    "tube": "LONDON_UNDERGROUND",
    "overground": "LONDON_OVERGROUND",
    "elizabeth-line": "ELIZABETH_LINE",
    "dlr": "LIGHT_RAILWAY",
    "tram": "TRAM",
    "national-rail": "NATIONAL_TRAIN",
}


def modes_to_rightmove_types(modes: list[str]) -> list[str]:
    """Translates a list of TfL mode strings to Rightmove `types` values,
    dropping any mode with no mapping (there shouldn't be any, since modes
    stored here always come from the same non-bus allowlist this maps) and
    preserving order without duplicates."""
    result = []
    for mode in modes:
        rightmove_type = _MODE_TO_RIGHTMOVE_TYPE.get(mode.strip())
        if rightmove_type and rightmove_type not in result:
            result.append(rightmove_type)
    return result
