#!/usr/bin/env bash
# Backfills crime-comparison data for every existing listing, via the real
# running container's GET /api/listings/{id}/crime endpoint — NOT a
# throwaway container. Each call there re-fetches (and caches) crime stats
# for that listing's postcode, plus any baseline postcode whose cache is
# missing or >30 days old (see app/crime/service.py's
# CACHE_MAX_AGE_DAYS) — so this is what you'd run once after configuring
# baselines in /admin, to warm the cache for your whole existing shortlist
# instead of paying the fetch cost one listing at a time as each detail
# page happens to be opened.
#
# Rate limiting: data.police.uk allows 15 req/s sustained, burst 30, and
# each crime fetch is ~13 calls (1 postcodes.io geocode + 12 months of
# crimes-street, one call per month — there's no date-range param). Every
# individual call is already throttled server-side
# (app/crime/client.py::_throttled_get: fixed delay + exponential backoff
# on 429), so the only extra thing THIS script must do to stay within
# limits is process listings strictly one at a time, waiting for each
# curl to finish before starting the next — never run this with xargs -P,
# background jobs (&), or any other parallelism.
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

baseline_count=$(curl -sf "$BASE_URL/api/crime/baselines" | jq 'length')
if [ "$baseline_count" -eq 0 ]; then
  echo "No crime baselines configured at $BASE_URL/admin — add at least one first." >&2
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

echo "About to fetch/cache crime data for $count listing(s) against $baseline_count"
echo "baseline(s) at $BASE_URL. Each uncached postcode is ~13 calls to"
echo "data.police.uk/postcodes.io, throttled server-side — this can take a"
echo "while (minutes, not seconds) for a shortlist of any size."
if [ "$ASSUME_YES" != true ]; then
  read -r -p "Continue? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

# Sequential on purpose -- see the rate-limiting note at the top of this
# file. Do not parallelize this loop.
for id in $ids; do
  resp=$(curl -sf "$BASE_URL/api/listings/$id/crime")
  unavailable=$(echo "$resp" | jq -r '.unavailable // empty')
  if [ -n "$unavailable" ]; then
    echo "listing $id: unavailable — $unavailable"
    continue
  fi
  errors=$(echo "$resp" | jq -r '[.baselines[] | select(.error != null) | .label] | join(", ")')
  ok_count=$(echo "$resp" | jq '[.baselines[] | select(.error == null)] | length')
  if [ -n "$errors" ]; then
    echo "listing $id: cached against $ok_count baseline(s), errors from: $errors"
  else
    echo "listing $id: cached against $ok_count baseline(s)"
  fi
done

echo
echo "Done."
