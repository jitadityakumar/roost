#!/usr/bin/env bash
# Mass re-fetches every existing listing from Rightmove, via the real
# running container's POST /api/listings/{id}/refresh endpoint — NOT a
# throwaway container. This is for bulk-refreshing listings (e.g. after a
# field-mapping change in app/jobs/rightmove_extract.py/handlers.py, or just
# to pull latest prices/status) instead of clicking Refresh on each one.
#
# By default, /refresh auto-chains media_download -> text_extract (and
# floor_area_vision/epc_vision off media_download) on its own, which means
# every re-fetch this script triggers already makes real, billed
# `claude -p` calls per listing in the background. Pass --skip-llm to opt
# out: /refresh?skip_llm=true (see routes/listings.py, handlers.py's
# skip_llm_chain check) still re-scrapes and re-downloads media, but never
# enqueues any llm-lane job — use this for a plain data backfill (e.g. after
# a rightmove_extract.py field-mapping change like adding a new field) where
# you don't want to pay for/wait on LLM re-extraction that has nothing to do
# with the change.
#
# --then-llm does NOT gate whether the llm-lane calls happen (that's
# --skip-llm's job) — it only controls whether this script *blocks* until
# whatever pipeline was actually enqueued finishes. Without --then-llm, the
# script returns as soon as rightmove_extract is enqueued and everything
# else keeps running in the background after it exits; with --then-llm, it
# waits for the whole pipeline (scrape -> media download -> whichever
# llm-lane jobs got auto-enqueued, none if --skip-llm) to actually finish
# before returning — useful before a UX review, or when you want one
# command's exit to mean "everything is done," not just "everything is
# queued." --then-llm and --skip-llm can be combined (waits for scrape +
# media only). This script never makes an extra explicit /llm-refresh call
# — that would double-run (and double-bill) work the auto-chain is already
# doing.
#
# rightmove_extract also recomputes station walking distances to every
# nearby station via TfL's free Unified API (issue #40) -- unconditional,
# no opt-out flag, unlike the old Google Routes API this replaced (which had
# a --skip-maps flag specifically to dodge its per-call billing).
#
# "and there is new data" (per the original ask) has no cheap way to be
# determined from outside the app (no snapshot diff exposed over the API) —
# a successful re-scrape (extraction_status == "done", not "failed") is
# treated as "there might be new data," the same assumption the in-app
# Refresh button itself makes.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8099}"
ASSUME_YES=false
ONLY_ID=""
THEN_LLM=false
SKIP_LLM=false
POLL_INTERVAL=3
POLL_TIMEOUT=180

usage() {
  echo "Usage: $0 [--base-url URL] [--listing-id ID] [--then-llm] [--skip-llm] [-y|--yes]"
  echo
  echo "  --base-url URL    Roost instance to target (default: $BASE_URL)"
  echo "  --listing-id ID   Only refresh this one listing, instead of all of them"
  echo "  --skip-llm        Re-scrape + re-download media only — don't auto-chain"
  echo "                    text_extract/floor_area_vision/epc_vision (no billed"
  echo "                    claude -p calls). Use for a plain data backfill."
  echo "  --then-llm        Block until each listing's full pipeline (Rightmove"
  echo "                    scrape + media download + whichever llm-lane jobs got"
  echo "                    auto-enqueued, none if --skip-llm) finishes, instead of"
  echo "                    returning as soon as the scrape is enqueued."
  echo "  -y, --yes         Skip the confirmation prompt"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --listing-id) ONLY_ID="$2"; shift 2 ;;
    --then-llm) THEN_LLM=true; shift ;;
    --skip-llm) SKIP_LLM=true; shift ;;
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
  echo "No listings found at $BASE_URL — nothing to refresh."
  exit 0
fi

echo "About to re-fetch $count listing(s) from Rightmove at $BASE_URL."
if [ "$SKIP_LLM" = true ]; then
  echo "--skip-llm set: no llm-lane jobs will be enqueued (no billed claude -p calls)."
else
  echo "This also auto-chains real, billed claude -p calls per listing (see script"
  echo "header) — pass --skip-llm to opt out."
fi
if [ "$THEN_LLM" = true ]; then
  echo "--then-llm set: this script will block until each listing's full pipeline finishes."
fi
if [ "$ASSUME_YES" != true ]; then
  read -r -p "Continue? [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

for id in $ids; do
  curl -sf -X POST "$BASE_URL/api/listings/$id/refresh?skip_llm=$SKIP_LLM" >/dev/null
  echo "listing $id: enqueued rightmove_extract"
done

if [ "$THEN_LLM" != true ]; then
  echo
  echo "Done enqueueing. Jobs (including auto-chained llm-lane jobs) process in the"
  echo "background — watch progress with: docker logs roost -f"
  exit 0
fi

# Waits for listing $1's rightmove_extract to leave queued/running, then for
# its most recent media_download job to also leave queued/running (or not
# exist within the timeout, e.g. if the job hasn't been enqueued yet), then
# for every llm-lane job still queued/running for this listing to settle too
# (covers whatever text_extract/floor_area_vision/epc_vision the scrape's own
# auto-chain enqueued — this function never enqueues anything itself).
# Prints "done", "failed" (scrape failed — no media/llm wait attempted), or
# "timeout" if any step didn't settle within POLL_TIMEOUT.
wait_for_pipeline() {
  local id="$1" status media_status llm_pending
  # Each stage gets its own fresh POLL_TIMEOUT budget -- these are
  # sequential, unrelated waits (Rightmove fetch, then media download, then
  # however many llm-lane jobs the auto-chain enqueued), not one combined
  # deadline. Sharing a single elapsed counter across all three would let a
  # slow early stage silently starve the last one -- typically the longest
  # and the one actually waiting on billed claude -p calls.
  local elapsed=0

  while [ "$elapsed" -lt "$POLL_TIMEOUT" ]; do
    status=$(curl -sf "$BASE_URL/api/listings/$id" | jq -r '.extraction_status')
    [ "$status" = "done" ] || [ "$status" = "failed" ] && break
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
  done
  if [ "$status" != "done" ] && [ "$status" != "failed" ]; then
    echo "timeout"; return
  fi
  if [ "$status" = "failed" ]; then
    echo "failed"; return
  fi

  elapsed=0
  while [ "$elapsed" -lt "$POLL_TIMEOUT" ]; do
    media_status=$(curl -sf "$BASE_URL/api/listings/$id/jobs" \
      | jq -r '[.[] | select(.job_type=="media_download")] | sort_by(.id) | last | .status // "missing"')
    if [ "$media_status" != "missing" ] && [ "$media_status" != "queued" ] && [ "$media_status" != "running" ]; then
      break
    fi
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
  done
  if [ "$media_status" = "missing" ] || [ "$media_status" = "queued" ] || [ "$media_status" = "running" ]; then
    echo "timeout"; return
  fi

  elapsed=0
  while [ "$elapsed" -lt "$POLL_TIMEOUT" ]; do
    llm_pending=$(curl -sf "$BASE_URL/api/listings/$id/jobs" \
      | jq '[.[] | select(.lane=="llm" and (.status=="queued" or .status=="running"))] | length')
    if [ "$llm_pending" -eq 0 ]; then
      echo "done"; return
    fi
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
  done
  echo "timeout"
}

echo
echo "Waiting for each listing's full pipeline to settle..."

for id in $ids; do
  result=$(wait_for_pipeline "$id")
  case "$result" in
    done) echo "listing $id: pipeline finished" ;;
    failed) echo "listing $id: Rightmove scrape failed" ;;
    timeout) echo "listing $id: timed out waiting for pipeline to settle (>${POLL_TIMEOUT}s)" ;;
  esac
done

echo
echo "Done."
