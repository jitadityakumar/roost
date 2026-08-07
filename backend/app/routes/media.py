import os
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import MEDIA_DIR
from app.listings import store

router = APIRouter(prefix="/api/listings", tags=["media"])

ALLOWED_CATEGORIES = {"photos", "floorplans", "epc"}
SAFE_FILENAME_RE = re.compile(r"^[\w.-]+$")


@router.get("/{listing_id}/media")
def list_media(listing_id: int):
    if store.get_listing(listing_id) is None:
        raise HTTPException(status_code=404, detail="listing not found")
    result = {}
    for category in ALLOWED_CATEGORIES:
        cat_dir = os.path.join(MEDIA_DIR, str(listing_id), category)
        result[category] = sorted(os.listdir(cat_dir)) if os.path.isdir(cat_dir) else []
    return result


@router.get("/{listing_id}/media/{category}/{filename}")
def get_media_file(listing_id: int, category: str, filename: str):
    if store.get_listing(listing_id) is None:
        raise HTTPException(status_code=404, detail="listing not found")
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=404, detail="unknown media category")
    if not SAFE_FILENAME_RE.match(filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    listing_dir = os.path.realpath(os.path.join(MEDIA_DIR, str(listing_id), category))
    path = os.path.realpath(os.path.join(listing_dir, filename))
    if os.path.dirname(path) != listing_dir or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)
