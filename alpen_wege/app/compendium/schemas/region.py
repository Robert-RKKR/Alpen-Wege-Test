from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas.geo import GeoPoint, GeoPointField, GeoPolygon, GeoPolygonField
from app.core.schemas.ref import RefWithFactorDetail, RefWithFactorRead
from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser
from app.compendium.schemas.country import CountryDetail, CountrySlimRead


FLAG_WRITE = "The flag or coat of arms: the id of an icon (`GET /assets/icons`, an SVG; the key of a canton flag is `flag_` + the ISO 3166-2 code in lower case with `_`, for example `flag_ch_zh`). Optional. An unknown id answers 422."
FLAG_READ = "Id of the flag or coat of arms (an icon, an SVG), or null. The picture: `GET /assets/icons/{icon_id}/file`."


class RegionCreate(BaseModel):
    name: str
    location: GeoPoint
    country_id: UUID
    region_type_id: UUID
    iso_code: str | None = None
    parent_id: UUID | None = None
    bbox: GeoPolygon | None = None
    icon_id: UUID | None = Field(None, description=FLAG_WRITE)
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
    icon_id: UUID | None = Field(None, description=FLAG_WRITE + " `null` removes the link; leave the field out to keep it.")
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
    icon_id: UUID | None = Field(description=FLAG_READ)


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
    icon_id: UUID | None = Field(description=FLAG_READ)
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


class RegionDetail(RegionRead):
    country: CountryDetail | None = Link()
    region_type: RefWithFactorDetail | None = Link()
    parent: "RegionDetail | None" = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
