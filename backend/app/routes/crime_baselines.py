from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.crime import service, store
from app.crime.client import CrimeApiError

router = APIRouter(prefix="/api/crime/baselines", tags=["crime"])


class CreateBaselineRequest(BaseModel):
    label: str
    postcode: str


class UpdateBaselineRequest(BaseModel):
    label: str
    postcode: str


@router.get("")
def list_baselines():
    return store.list_baselines()


@router.post("", status_code=201)
def create_baseline(body: CreateBaselineRequest):
    try:
        service.get_or_refresh_stats(body.postcode)
    except CrimeApiError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        return store.create_baseline(body.label, body.postcode)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{baseline_id}")
def update_baseline(baseline_id: int, body: UpdateBaselineRequest):
    try:
        service.get_or_refresh_stats(body.postcode)
    except CrimeApiError as e:
        raise HTTPException(status_code=422, detail=str(e))
    updated = store.update_baseline(baseline_id, body.label, body.postcode)
    if updated is None:
        raise HTTPException(status_code=404, detail="baseline not found")
    return updated


@router.delete("/reference", status_code=204)
def clear_reference_baseline():
    store.clear_reference_baseline()


@router.delete("/{baseline_id}", status_code=204)
def delete_baseline(baseline_id: int):
    store.delete_baseline(baseline_id)


@router.post("/{baseline_id}/reference")
def set_reference_baseline(baseline_id: int):
    updated = store.set_reference_baseline(baseline_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="baseline not found")
    return updated
