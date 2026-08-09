from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.crime import service, store
from app.crime.client import CrimeApiError

router = APIRouter(prefix="/api/crime/baselines", tags=["crime"])


class CreateBaselineRequest(BaseModel):
    label: str
    postcode: str


@router.get("")
def list_baselines():
    return store.list_baselines()


@router.post("", status_code=201)
def create_baseline(body: CreateBaselineRequest):
    if len(store.list_baselines()) >= store.MAX_BASELINES:
        raise HTTPException(status_code=422, detail=f"only {store.MAX_BASELINES} baselines are allowed")
    try:
        service.get_or_refresh_stats(body.postcode)
    except CrimeApiError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        return store.create_baseline(body.label, body.postcode)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{baseline_id}", status_code=204)
def delete_baseline(baseline_id: int):
    store.delete_baseline(baseline_id)
