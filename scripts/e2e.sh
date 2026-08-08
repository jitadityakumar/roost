#!/usr/bin/env bash
# Runs the Playwright e2e suite against a throwaway Roost container — NOT
# the real production container on port 8099. Builds the image fresh, runs
# it on a different port with a temp data directory (so nothing touches
# ~/github/roost/data), runs the tests, then tears the container down.
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE_TAG="roost-e2e-test"
CONTAINER_NAME="roost-e2e-test"
HOST_PORT=8199
DATA_DIR="$(mktemp -d)"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  rm -rf "$DATA_DIR"
}
trap cleanup EXIT

echo "Building image..."
docker build -t "$IMAGE_TAG" .

echo "Starting throwaway container on port $HOST_PORT (data dir: $DATA_DIR)..."
docker run -d --name "$CONTAINER_NAME" \
  -p "$HOST_PORT:8000" \
  -v "$DATA_DIR:/data" \
  "$IMAGE_TAG" >/dev/null

echo "Waiting for the app to become healthy..."
for _ in $(seq 1 30); do
  if curl -sf "http://localhost:$HOST_PORT/api/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -sf "http://localhost:$HOST_PORT/api/health" >/dev/null || {
  echo "App did not become healthy in time" >&2
  docker logs "$CONTAINER_NAME" >&2
  exit 1
}

cd e2e
npm install --quiet
ROOST_E2E_BASE_URL="http://localhost:$HOST_PORT" npx playwright test "$@"
