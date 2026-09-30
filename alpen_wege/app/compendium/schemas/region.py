from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.schemas.geo import GeoPoint, GeoPointField, GeoPolygon, GeoPolygonField
from app.core.schemas.ref import RefWithFactorRead
from app.compendium.schemas.country import CountrySlimRead


class RegionCreate(BaseModel):
    name: str
    location: GeoPoint
    country_id: UUID
    region_type_id: UUID
    iso_code: str | None = None
    parent_id: UUID | None = None
    bbox: GeoPolygon | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class RegionUpdate(BaseModel):
    name: str | None = None
    location: GeoPoint | None = None
    country_id: UUID | None = None
    region_type_id: UUID | None = None
    iso_code: str | None = None
    parent_id: UUID | None = None
    bbox: GeoPolygon | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class RegionSlimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    location: GeoPointField = None
    iso_code: str | None


class RegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    location: GeoPointField = None
    country_id: UUID
    country: CountrySlimRead | None = None
    region_type_id: UUID
    region_type: RefWithFactorRead | None = None
    iso_code: str | None
    parent_id: UUID | None
    parent: RegionSlimRead | None = None
    bbox: GeoPolygonField = None
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
