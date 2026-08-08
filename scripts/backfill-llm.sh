#!/usr/bin/env bash
# Re-runs the llm-lane jobs (text_extract, floor_area_vision, epc_vision)
# against every existing listing, via the real running container's
# POST /api/listings/{id}/llm-refresh endpoint — NOT a throwaway container.
# This is for backfilling real data after a model/prompt/schema change in
# app/jobs/llm_client.py or llm_prompts.py: it makes real, billed `claude -p`
# calls per listing per applicable job type, and overwrites any existing
# llm-sourced field values with fresh output (hand-edited fields and
# rightmove-sourced fields are protected — see llm_refresh_listing's
# docstring in app/routes/listings.py).
#
# Enqueues only — the llm lane is strictly serial (one worker), so jobs
# process one at a time in the background after this script exits. Check
# progress with `docker logs roost -f` or the printed per-listing job list.
#
# To test a brand-new listing instead of backfilling existing ones, just
# submit it normally through the app — the same llm-lane jobs auto-chain
# for new listings already, no script needed.
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

echo "About to re-run llm-lane jobs (text_extract, floor_area_vision, epc_vision)"
echo "against $count listing(s) at $BASE_URL."
echo "This makes real, billed claude -p calls and overwrites existing llm-sourced fields."
if [ "$ASSUME_YES" != true ]; then
  read -r -p "Continue? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

for id in $ids; do
  resp=$(curl -sf -X POST "$BASE_URL/api/listings/$id/llm-refresh")
  enqueued=$(echo "$resp" | jq -r '.enqueued | join(", ")')
  if [ -z "$enqueued" ]; then
    echo "listing $id: nothing to enqueue (all fields sticky, or no images on disk)"
  else
    echo "listing $id: enqueued $enqueued"
  fi
done

echo
echo "Done enqueueing. Jobs process one at a time in the background —"
echo "watch progress with: docker logs roost -f"
