import os

BASE_DATA_DIR = os.environ.get(
    "ROOST_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"),
)
MEDIA_DIR = os.path.join(BASE_DATA_DIR, "media")

# No default -- unlike MEDIA_DIR, there's no sane in-repo fallback for a
# separate service's address (it's a personal Tailscale/LAN endpoint, not
# something a public repo should hardcode). Required at call time, not
# import time -- see app/commute/client.py.
COMMUTE_API_BASE = os.environ.get("ROOST_COMMUTE_API_BASE")

# Same reasoning as COMMUTE_API_BASE -- see app/mortgage/client.py.
MORTGAGE_API_BASE = os.environ.get("ROOST_MORTGAGE_API_BASE")

# TfL's free Unified API key -- see app/commute/tfl_client.py. No in-repo
# default; a missing key means walk distances/frequent-destination journeys
# just aren't computed (caught and logged per-call, not fatal).
TFL_API_KEY = os.environ.get("TFL_API_KEY")

# User's home lat/lon, for the home-vs-listing journey duration comparison
# (see app/destinations/compute.py) -- deliberately an env var, never
# DB-stored, so a real home address never ends up in the public repo or a
# shared DB dump. No in-repo default; either var missing or unparseable as
# a float means the comparison just isn't computed/shown, same
# caught-and-skipped precedent as TFL_API_KEY.
def _parse_coord(name: str) -> float | None:
    value = os.environ.get(name)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


HOME_LAT = _parse_coord("ROOST_HOME_LAT")
HOME_LON = _parse_coord("ROOST_HOME_LON")
