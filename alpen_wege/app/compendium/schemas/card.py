from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas.ref import (
    CompendiumTypeDetail, DifficultySportDetail, DifficultySportRead, RefRankedDetail, RefRankedRead, RefWithFactorRead,
)
from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser
from app.compendium.schemas.poi import PoiDetail, PoiSlimRead


class CardCreate(BaseModel):
    card_number: int | None = Field(None, gt=0, le=2_147_483_647, description="Leave out: the next free number is assigned.")
    name: str | None = None
    rarity_id: UUID | None = None
    compendium_type_id: UUID | None = None
    poi_id: UUID
    main_photo_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class CardUpdate(BaseModel):
    card_number: int | None = Field(None, gt=0, le=2_147_483_647)
    name: str | None = None
    rarity_id: UUID | None = None
    compendium_type_id: UUID | None = None
    poi_id: UUID | None = None
    main_photo_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None

    @field_validator("poi_id", "card_number", mode="before")
    @classmethod
    def reject_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be set to null")
        return v


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    card_number: int
    name: str | None
    rarity_id: UUID | None
    rarity: RefRankedRead | None = None
    compendium_type_id: UUID | None
    compendium_type: RefWithFactorRead | None = None
    poi_id: UUID
    poi: PoiSlimRead | None = None
    main_photo_id: UUID | None
    difficulty_level_id: UUID | None
    difficulty_level: RefRankedRead | None = None
    difficulty_sport_id: UUID | None
    difficulty_sport: DifficultySportRead | None = None
    render_status: str | None
    render_version: int | None
    rendered_at: datetime | None
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
    difficulty_level: RefRankedDetail | None = Link()
    difficulty_sport: DifficultySportDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
