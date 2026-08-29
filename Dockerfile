# --- Stage 1: build the React frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend, serving the built frontend as static files ---
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist ./static

ENV ROOST_DATA_DIR=/data
VOLUME /data
EXPOSE 8000

# Phase 3 (LLM enrichment): the llm-lane worker no longer shells out to the
# `claude` CLI locally (issue #73) — it calls a host-resident LLM bridge
# (host/llm_bridge/) over HTTP instead, via ROOST_LLM_BRIDGE_BASE. The
# container never touches `~/.claude` at all any more, so there's no Node/
# CLI install and no `~/.claude` mount here.
#
# Run with: docker run -p 8099:8000 -v $(pwd)/data:/data \
#   --add-host=host.docker.internal:host-gateway \
#   --env-file .env roost
# (.env sets ROOST_LLM_BRIDGE_BASE=http://host.docker.internal:8094)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
