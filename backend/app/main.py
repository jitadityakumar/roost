import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
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
# (copied from the frontend build stage). Mounted last so it only catches
# requests the routers above didn't already handle. In local dev (frontend
# served separately by `npm run dev`), this directory doesn't exist.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
