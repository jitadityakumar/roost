#!/usr/bin/env bash
# Runs the backend (pytest) and frontend (vitest) suites — the fast local
# checks to run after every change. Does NOT run e2e (see scripts/e2e.sh),
# which needs a real Docker container and is slower/more involved.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Backend: pytest"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt -r backend/requirements-dev.txt
backend/.venv/bin/pytest backend/tests/ -v

echo "==> Frontend: vitest"
(cd frontend && npm install --silent && npm run test)

echo "==> All tests passed."
