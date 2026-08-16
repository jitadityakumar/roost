#!/usr/bin/env bash
# Recomputes station walking distances for every existing listing, via the
# real running container's POST /api/listings/{id}/walk-refresh endpoint --
# NOT a throwaway container, and NOT a Rightmove re-scrape. For backfilling
# after a walk-distance-computation change (issue #40 PR2's station_index
# schema/mode-mapping rewrite is the case this was written for) where
# nearest_stations_raw/latitude/longitude haven't changed, only how walk
# distance is computed from them -- same "recompute from what's already
# stored" precedent as scripts/backfill-llm.sh for the llm lane.
#
# Rate limiting: TfL's registered-key cap is 500 req/min.
# app/commute/tfl_client.py's throttle is module-level inside the running
# container's own Python process and applies regardless of what's calling
# in (a bulk backfill or a single manual refresh) -- this script doesn't
# need its own delay/batching on top of that. It still issues requests one
# listing at a time (not parallelized) purely so output stays readable and
# a single stuck request doesn't strand others mid-flight; it's not load-
# bearing for the rate limit itself.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8099}"
ASSUME_YES=false
ONLY_ID=""

usage() {
  echo "Usage: $0 [--base-url URL] [--listing-id ID] [-y|--yes]"
  echo
  echo "  --base-url URL    Roost instance to target (default: $BASE_URL)"
  echo "  --listing-id ID   Only backfill this one listing, instead of all of them"
  echo "  -y, --yes         Skip the confirmation prompt"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --listing-id) ONLY_ID="$2"; shift 2 ;;
    -y|--yes) ASSUME_YES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if ! curl -sf "$BASE_URL/api/health" >/dev/null; then
  echo "Could not reach $BASE_URL/api/health — is the container running?" >&2
  exit 1
fi

if [ -n "$ONLY_ID" ]; then
  ids="$ONLY_ID"
else
  ids=$(curl -sf "$BASE_URL/api/listings" | jq -r '.[].id')
fi

count=$(echo "$ids" | grep -c . || true)
if [ "$count" -eq 0 ]; then
  echo "No listings found at $BASE_URL — nothing to backfill."
  exit 0
fi

echo "About to recompute walk distances for $count listing(s) against"
echo "$BASE_URL — no Rightmove re-scrape, real TfL API calls."
if [ "$ASSUME_YES" != true ]; then
  read -r -p "Continue? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

for id in $ids; do
  resp=$(curl -sf -X POST "$BASE_URL/api/listings/$id/walk-refresh")
  stations=$(echo "$resp" | jq -r '[.nearest_stations_raw[]? | select(.walk_distance_meters != null)] | length')
  total=$(echo "$resp" | jq -r '.nearest_stations_raw | length')
  echo "listing $id: walk data for $stations/$total station(s)"
done

echo
echo "Done."
