from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.schemas.ref import CompendiumTypeDetail, RefRankedDetail, RefRankedRead, RefWithFactorRead
from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser
from app.compendium.schemas.poi import PoiDetail, PoiSlimRead


class CardCreate(BaseModel):
    name: str | None = None
    rarity_id: UUID | None = None
    compendium_type_id: UUID | None = None
    poi_id: UUID
    main_photo_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class CardUpdate(BaseModel):
    name: str | None = None
    rarity_id: UUID | None = None
    compendium_type_id: UUID | None = None
    poi_id: UUID | None = None
    main_photo_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None

    @field_validator("poi_id", mode="before")
    @classmethod
    def reject_null_poi(cls, v):
        if v is None:
            raise ValueError("poi_id cannot be set to null")
        return v


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    rarity_id: UUID | None
    rarity: RefRankedRead | None = None
    compendium_type_id: UUID | None
    compendium_type: RefWithFactorRead | None = None
    poi_id: UUID
    poi: PoiSlimRead | None = None
    main_photo_id: UUID | None
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


class CardDetail(CardRead):
    rarity: RefRankedDetail | None = Link()
    compendium_type: CompendiumTypeDetail | None = Link()
    poi: PoiDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
