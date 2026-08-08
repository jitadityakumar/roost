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

# Phase 3 (LLM enrichment): the llm-lane worker shells out to the `claude`
# CLI, which needs Node. Credentials are NOT baked into the image or passed
# as an env var — the container expects the host's `claude login` session
# mounted read-only at /root/.claude (see run command below), reusing the
# same Claude Code auth already set up on the host rather than provisioning
# a separate ANTHROPIC_API_KEY.
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g @anthropic-ai/claude-code@2.1.226 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist ./static

ENV ROOST_DATA_DIR=/data
VOLUME /data
EXPOSE 8000

# Run with: docker run -p 8099:8000 -v $(pwd)/data:/data \
#   -v ~/.claude:/root/.claude:ro roost
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
