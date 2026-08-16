#!/usr/bin/env bash
# Recomputes Frequent Destinations journeys -- destination_journeys (every
# listing x every destination) and home_journeys (one row per destination,
# from ROOST_HOME_LAT/ROOST_HOME_LON) -- via the real running container's
# API, NOT a throwaway container. Written for issue #51 (LeastInterchange +
# non-bus mode allowlist), but reusable any time the journey-computation
# logic changes and existing stored rows need to reflect it -- same
# "recompute from what's already stored, the underlying source data hasn't
# changed" precedent as scripts/tfl-walk-backfill.sh and
# scripts/backfill-llm.sh.
#
# Two modes:
#   Full (default): PATCHes every destination with a no-op value (its own
#   current name), which re-triggers compute_for_destination -- the same
#   mechanism the admin UI itself uses for a create/edit, routed through
#   backfill_queue's single global FIFO worker. This recomputes every
#   listing x destination pair AND that destination's home journey in one
#   pass, and polls GET .../backfill-status until each destination finishes
#   before moving to the next.
#
#   Sample (--listing-limit N): for testing a change against a handful of
#   listings before committing to the full (slow) backfill. Only the first
#   N listings (by id) are recomputed, via POST
#   /api/listings/{id}/destinations/refresh (recomputes every destination
#   for that one listing, synchronously) -- NOT the full-destination PATCH
#   path above, which has no way to scope itself to a subset of listings.
#   Each configured destination's home journey is also recomputed once, via
#   POST /api/destinations/{id}/home-refresh (issue #51 addition) -- home
#   has no per-listing loop to sample, so this always runs in full
#   regardless of --listing-limit.
#
# Rate limiting: no delay/batching logic here -- app/commute/tfl_client.py's
# module-level throttle (~400-450 req/min, under TfL's 500/min cap) lives
# inside the running container's own Python process and applies to every
# caller regardless of what's asking, same as tfl-walk-backfill.sh. This
# script still issues requests one destination/listing at a time (never in
# parallel) purely so output stays readable and a single stuck request
# doesn't strand others mid-flight -- not because it's needed for the rate
# cap itself.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8099}"
ASSUME_YES=false
LISTING_LIMIT=""

usage() {
  echo "Usage: $0 [--base-url URL] [--listing-limit N] [-y|--yes]"
  echo
  echo "  --base-url URL       Roost instance to target (default: $BASE_URL)"
  echo "  --listing-limit N    Sample mode: only recompute the first N listings"
  echo "                       (by id), instead of the full backfill. Home"
  echo "                       journeys are always recomputed in full."
  echo "  -y, --yes            Skip the confirmation prompt"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --listing-limit) LISTING_LIMIT="$2"; shift 2 ;;
    -y|--yes) ASSUME_YES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if ! curl -sf "$BASE_URL/api/health" >/dev/null; then
  echo "Could not reach $BASE_URL/api/health — is the container running?" >&2
  exit 1
fi

destinations_json=$(curl -sf "$BASE_URL/api/destinations")
destination_count=$(echo "$destinations_json" | jq 'length')
if [ "$destination_count" -eq 0 ]; then
  echo "No destinations found at $BASE_URL — nothing to backfill."
  exit 0
fi

if [ -n "$LISTING_LIMIT" ]; then
  listing_ids=$(curl -sf "$BASE_URL/api/listings" | jq -r 'sort_by(.id) | .[].id' | head -n "$LISTING_LIMIT")
  listing_count=$(echo "$listing_ids" | grep -c . || true)
  echo "Sample mode: recomputing $listing_count listing(s) x $destination_count destination(s),"
  echo "plus $destination_count home journey(s), against $BASE_URL."
else
  echo "Full backfill: recomputing every listing x $destination_count destination(s),"
  echo "plus $destination_count home journey(s), against $BASE_URL. This can take a"
  echo "while -- TfL's journey-scan cost is per listing x destination."
fi
if [ "$ASSUME_YES" != true ]; then
  read -r -p "Continue? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

if [ -n "$LISTING_LIMIT" ]; then
  for listing_id in $listing_ids; do
    resp=$(curl -sf -X POST "$BASE_URL/api/listings/$listing_id/destinations/refresh")
    resolved=$(echo "$resp" | jq '[.[] | select(.resolved)] | length')
    total=$(echo "$resp" | jq 'length')
    echo "listing $listing_id: $resolved/$total destination(s) resolved"
  done
else
  destination_ids=$(echo "$destinations_json" | jq -r '.[].id')
  for destination_id in $destination_ids; do
    name=$(echo "$destinations_json" | jq -r ".[] | select(.id == $destination_id) | .name")
    curl -sf -X PATCH "$BASE_URL/api/destinations/$destination_id" \
      -H 'Content-Type: application/json' \
      -d "$(jq -n --arg name "$name" '{name: $name}')" >/dev/null

    # Bounded, not an infinite spin -- a hung backfill_queue worker (never
    # observed, but nothing rules it out) would otherwise leave this loop
    # running forever with only Ctrl-C as an escape. 900 * 2s = 30min, well
    # beyond any backfill this app has ever taken (context.md: full 68-listing
    # backfills complete in well under a minute per destination historically).
    max_polls=900
    polls=0
    while :; do
      status=$(curl -sf "$BASE_URL/api/destinations/$destination_id/backfill-status")
      state=$(echo "$status" | jq -r '.status')
      done_count=$(echo "$status" | jq -r '.done')
      total_count=$(echo "$status" | jq -r '.total')
      case "$state" in
        queued|running)
          polls=$((polls + 1))
          if [ "$polls" -ge "$max_polls" ]; then
            echo "destination $destination_id ($name): still '$state' after ${max_polls} polls (~30min) -- giving up, check the container logs" >&2
            break
          fi
          printf "\rdestination %s (%s): %s/%s" "$destination_id" "$name" "$done_count" "$total_count"
          sleep 2
          ;;
        done|failed)
          printf "\rdestination %s (%s): %s (%s/%s)\n" "$destination_id" "$name" "$state" "$done_count" "$total_count"
          break
          ;;
        *)
          echo "destination $destination_id ($name): unexpected status '$state'" >&2
          break
          ;;
      esac
    done
  done
fi

# Home journeys: always recomputed in full, regardless of --listing-limit --
# there's no per-listing dimension to sample here, and the full-backfill
# path above already covers it via compute_for_destination.
if [ -n "$LISTING_LIMIT" ]; then
  destination_ids=$(echo "$destinations_json" | jq -r '.[].id')
  for destination_id in $destination_ids; do
    resp=$(curl -sf -X POST "$BASE_URL/api/destinations/$destination_id/home-refresh")
    resolved=$(echo "$resp" | jq -r '.resolved')
    echo "destination $destination_id: home journey resolved=$resolved"
  done
fi

echo
echo "Done."
