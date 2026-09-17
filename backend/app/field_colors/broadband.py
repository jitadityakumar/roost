"""Parses Rightmove's broadband "fastestAverageSpeed.display" string (e.g.
"900Mb", "900 Mb", "900Mbps") down to a bare Mbps integer for the
broadband_top_speed_mbps column (issue #100). Mirrors the regex
ListingDetail.jsx's formatBroadband() already uses for display -- pulled out
to a shared backend parser since storage-time parsing needs the same speed
number the frontend strips a unit suffix from at render time."""
import re

_SPEED_RE = re.compile(r"([\d.]+)\s*mb", re.IGNORECASE)


def parse_broadband_mbps(raw) -> int | None:
    if not raw:
        return None
    match = _SPEED_RE.search(str(raw))
    if not match:
        return None
    try:
        return round(float(match.group(1)))
    except ValueError:
        return None
