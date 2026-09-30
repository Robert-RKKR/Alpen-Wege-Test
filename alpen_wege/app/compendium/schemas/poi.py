from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.schemas.geo import GeoPoint, GeoPointField
from app.core.schemas.ref import RefWithFactorRead
from app.compendium.schemas.region import RegionSlimRead


class PoiCreate(BaseModel):
    name: str
    location: GeoPoint
    compendium_type_id: UUID
    main_region_id: UUID
    altitude_m: int | None = None
    data_source_url: str | None = None
    poi_access_id: UUID | None = None
    main_photo_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class PoiUpdate(BaseModel):
    name: str | None = None
    location: GeoPoint | None = None
    compendium_type_id: UUID | None = None
    main_region_id: UUID | None = None
    altitude_m: int | None = None
    data_source_url: str | None = None
    poi_access_id: UUID | None = None
    main_photo_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class PoiSlimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    location: GeoPointField = None
    altitude_m: int | None


class PoiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    location: GeoPointField = None
    altitude_m: int | None
    data_source_url: str | None
    compendium_type_id: UUID
    compendium_type: RefWithFactorRead | None = None
    poi_access_id: UUID | None
    main_photo_id: UUID | None
    main_region_id: UUID
    main_region: RegionSlimRead | None = None
    name_de: str | None
    name_pl: str | None
    summary: str | None
    summary_de: str | None
    summary_pl: str | None
    description: str | None
    description_de: str | None
    description_pl: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
