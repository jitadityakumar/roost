from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.detail_sections import store

router = APIRouter(prefix="/api", tags=["detail_sections"])


class DetailSectionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    details_expanded: bool
    description_features_expanded: bool
    nearest_stations_expanded: bool
    floorplans_expanded: bool
    epc_expanded: bool
    room_sizes_expanded: bool
    commute_expanded: bool
    frequent_destinations_expanded: bool
    mortgage_expanded: bool
    crime_expanded: bool
    jobs_expanded: bool
    local_politics_expanded: bool


@router.get("/admin/detail-page-sections")
def get_sections_config():
    return store.get_config()


@router.put("/admin/detail-page-sections")
def put_sections_config(body: DetailSectionsConfig):
    return store.put_config(body.model_dump())
