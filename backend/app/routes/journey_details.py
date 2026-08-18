from fastapi import APIRouter, HTTPException

from app.destinations import journey_store, store
from app.destinations.journey_detail import parse_candidate

router = APIRouter(prefix="/api/journey-scan-pools", tags=["journey-details"])


@router.get("/{pool_id}")
def get_scan_pool(pool_id: int):
    pool = journey_store.get_scan_pool(pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail="journey scan pool not found")
    destination = next((d for d in store.list_destinations() if d["id"] == pool["destination_id"]), None)
    return {
        "destination_name": destination["name"] if destination else None,
        "scanned_at": pool["scanned_at"],
        "query_params": pool["query_params"],
        "candidates": [parse_candidate(j) for j in pool["candidate_pool"]],
    }
