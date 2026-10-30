from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


ICON_KEY_PATTERN = r"^[a-z0-9_.-]{1,100}$"   # lower case only; the database has the same rule (ck_asset_agg_icon_key)


class IconUpdate(BaseModel):
    # the SVG itself is replaced with PUT /assets/icons/{id}/file
    name: str | None = Field(None, min_length=1, max_length=255)
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    key: str | None = Field(None, pattern=ICON_KEY_PATTERN, description="Lower-case letters, digits and _ . - only, 1 to 100 characters. Upper case is turned into lower case.")

    @field_validator("key", mode="before")
    @classmethod
    def _lower_case_key(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class IconRead(BaseModel):
    # the SVG text is not part of the JSON: read it with GET /assets/icons/{id}/file
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    name_de: str | None
    name_pl: str | None
    summary: str | None
    summary_de: str | None
    summary_pl: str | None
    key: str
    sha256: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class IconDetail(IconRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class IconImportResult(BaseModel):
    dry_run: bool = Field(description="true: everything was checked and counted, nothing was saved")
    inserted: int = Field(description="icons created (their key was new)")
    updated: int = Field(description="existing icons replaced (only with update=true and when the SVG or a name differs)")
    unchanged: int = Field(description="existing icons left as they are")
    rejected: int = Field(description="rows that were not used; each is listed in errors")
    errors: list[str] = Field(description='one text per rejected row, for example "row 7 (sport_x): not valid XML ..." (the first 200)')
    notes: list[str] = Field(description="what the cleaner took out of an accepted row (script, style, external links, ...), one text per icon (the first 200)")
    linked: dict[str, int] | None = Field(None, description="with link=true: rows that got icon_id, per table (country, region, sport type, ...); tables with nothing new are left out")
    still_without_icon: dict[str, int] | None = Field(None, description="with link=true: rows that still have no icon, per table")


class IconLinkResult(BaseModel):
    dry_run: bool
    linked: dict[str, int] = Field(description="rows that got icon_id now, per table; tables with nothing new are left out")
    still_without_icon: dict[str, int] = Field(description="countries and regions that still have no icon (no icon with their key exists yet)")


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
