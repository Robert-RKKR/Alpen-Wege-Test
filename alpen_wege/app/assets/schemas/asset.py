from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas.geo import GeoPoint, GeoPointField
from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser


class PhotoUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    location: GeoPoint | None = None
    altitude_m: int | None = Field(None, ge=-500, le=9000)
    taken_at: datetime | None = None
    is_public: bool | None = None


class PhotoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    name_de: str | None
    name_pl: str | None
    summary: str | None
    summary_de: str | None
    summary_pl: str | None
    location: GeoPointField = None
    altitude_m: int | None
    taken_at: datetime | None
    path: str
    is_public: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class PhotoDetail(PhotoRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class GpxUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    is_public: bool | None = None


class GpxRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    name_de: str | None
    name_pl: str | None
    summary: str | None
    summary_de: str | None
    summary_pl: str | None
    path: str
    sha256: str | None
    size_bytes: int | None
    is_public: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class GpxDetail(GpxRead):
    created_by_user: ExpandedUser | None = Link("created_by")
