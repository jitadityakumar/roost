from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.field_colors import store

router = APIRouter(prefix="/api/admin/field-color-thresholds", tags=["field_colors"])


class UpsertThresholdRequest(BaseModel):
    green_cutoff: str | None = None
    red_cutoff: str | None = None
    higher_is_better: bool | None = None


@router.get("")
def list_thresholds():
    return store.list_thresholds()


@router.put("/{field}")
def upsert_threshold(field: str, body: UpsertThresholdRequest):
    try:
        return store.upsert_threshold(field, body.green_cutoff, body.red_cutoff, body.higher_is_better)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{field}", status_code=204)
def delete_threshold(field: str):
    store.delete_threshold(field)
