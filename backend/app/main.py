import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.migrate import run_migrations
from app.jobs.worker import HttpLaneWorkerPool
from app.routes import listings, media

logging.basicConfig(level=logging.INFO)

worker_pool = HttpLaneWorkerPool()


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    worker_pool.start()
    yield
    await worker_pool.stop()


app = FastAPI(title="Roost", lifespan=lifespan)
app.include_router(listings.router)
app.include_router(media.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# In the packaged Docker image, the built frontend lands in ./static
# (copied from the frontend build stage). In local dev (frontend served
# separately by `npm run dev`), this directory doesn't exist.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    # Built JS/CSS bundles only — not mounted at "/", so it never shadows
    # the SPA-fallback route below.
    app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIR, "assets")), name="assets")

    # The frontend uses client-side routing (react-router), and every page
    # (including /listings/{id}) needs to be a real, shareable, directly
    # loadable URL. A plain StaticFiles(html=True) mount only resolves
    # index.html for "/" and real directories, so a fresh load of e.g.
    # /active or /listings/123 would 404. This catch-all always serves
    # index.html for anything that isn't an API route or a known static
    # asset, letting react-router take over client-side.
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # A real API 404 (e.g. /api/nonexistent) should stay a 404, not
        # silently serve the app shell.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        if full_path == "favicon.svg":
            return FileResponse(os.path.join(_STATIC_DIR, "favicon.svg"))
        index_path = os.path.join(_STATIC_DIR, "index.html")
        if not os.path.isfile(index_path):
            raise HTTPException(status_code=404)
        return FileResponse(index_path)
