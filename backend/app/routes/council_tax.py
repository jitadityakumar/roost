from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.counciltax import store

router = APIRouter(prefix="/api/council-tax", tags=["council-tax"])


class UpsertRatesRequest(BaseModel):
    council_name: str
    band_a: float | None = None
    band_b: float | None = None
    band_c: float | None = None
    band_d: float | None = None
    band_e: float | None = None
    band_f: float | None = None
    band_g: float | None = None
    band_h: float | None = None


@router.get("")
def list_councils():
    return store.list_councils()


@router.put("/{gss_code}")
def upsert_rates(gss_code: str, body: UpsertRatesRequest):
    if not body.council_name.strip():
        raise HTTPException(status_code=422, detail="council_name is required")
    bands = {
        "band_a": body.band_a,
        "band_b": body.band_b,
        "band_c": body.band_c,
        "band_d": body.band_d,
        "band_e": body.band_e,
        "band_f": body.band_f,
        "band_g": body.band_g,
        "band_h": body.band_h,
    }
    return store.upsert_rates(gss_code, body.council_name.strip(), bands)


@router.delete("/{gss_code}", status_code=204)
def delete_council(gss_code: str):
    store.delete_council(gss_code)
