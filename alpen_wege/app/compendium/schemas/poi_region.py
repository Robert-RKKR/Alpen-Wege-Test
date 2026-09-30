from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.compendium.schemas.poi import PoiSlimRead
from app.compendium.schemas.region import RegionSlimRead


class PoiRegionCreate(BaseModel):
    poi_id: UUID
    region_id: UUID
    slot_position: int


class PoiRegionUpdate(BaseModel):
    poi_id: UUID | None = None
    region_id: UUID | None = None
    slot_position: int | None = None


class PoiRegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    poi_id: UUID
    poi: PoiSlimRead | None = None
    region_id: UUID
    region: RegionSlimRead | None = None
    slot_position: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
