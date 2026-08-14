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

# Reused from the rail-disruption-monitor project's own key -- see
# app/commute/walking.py. No in-repo default; a missing key means walk
# distances just aren't computed (caught and logged per-station, not fatal).
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

# Same reasoning as COMMUTE_API_BASE -- see app/destinations/client.py.
TRAIN_PLANNER_BASE = os.environ.get("ROOST_TRAIN_PLANNER_BASE")
