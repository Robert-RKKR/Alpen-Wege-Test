from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.schemas.geo import GeoPoint, GeoPointField
from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser


class CountryCreate(BaseModel):
    name: str
    iso_code: str
    location: GeoPoint
    name_common: str | None = None
    name_common_de: str | None = None
    name_common_pl: str | None = None
    name_official: str | None = None
    name_official_de: str | None = None
    name_official_pl: str | None = None
    name_native_common: list[str] | None = None
    name_native_official: list[str] | None = None
    languages: list[str] | None = None
    currencies: list[str] | None = None
    capital: str | None = None
    capital_de: str | None = None
    capital_pl: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class CountryUpdate(BaseModel):
    name: str | None = None
    iso_code: str | None = None
    location: GeoPoint | None = None
    name_common: str | None = None
    name_common_de: str | None = None
    name_common_pl: str | None = None
    name_official: str | None = None
    name_official_de: str | None = None
    name_official_pl: str | None = None
    name_native_common: list[str] | None = None
    name_native_official: list[str] | None = None
    languages: list[str] | None = None
    currencies: list[str] | None = None
    capital: str | None = None
    capital_de: str | None = None
    capital_pl: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class CountrySlimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    iso_code: str
    location: GeoPointField = None


class CountryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    iso_code: str
    location: GeoPointField = None
    name_common: str | None
    name_common_de: str | None
    name_common_pl: str | None
    name_official: str | None
    name_official_de: str | None
    name_official_pl: str | None
    name_native_common: list[str] | None
    name_native_official: list[str] | None
    languages: list[str] | None
    currencies: list[str] | None
    capital: str | None
    capital_de: str | None
    capital_pl: str | None
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


class CountryDetail(CountryRead):
    created_by_user: ExpandedUser | None = Link("created_by")
