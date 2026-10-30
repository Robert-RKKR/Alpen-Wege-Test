from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser


ICON_ID_WRITE = "The picture of this value: the id of an icon (`GET /assets/icons`, an SVG). An unknown id answers 422."
ICON_ID_KEEP = " Leave the field out to keep the icon; it cannot be removed (`null` answers 422)."
ICON_ID_READ = "Id of the icon (an SVG) of this value. The picture: `GET /assets/icons/{icon_id}/file`."


class RefBaseCreate(BaseModel):
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str
    icon_id: UUID = Field(description=ICON_ID_WRITE)


class RefBaseUpdate(BaseModel):
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str | None = None
    icon_id: UUID | None = Field(None, description=ICON_ID_WRITE + ICON_ID_KEEP)

    @model_validator(mode="after")
    def _required_columns_cannot_be_set_to_null(self):
        # "not sent" means "unchanged"; an explicit null on a NOT NULL column used to end in a database error (500)
        for field in ("color", "icon_id", "point_factor", "rank"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null; leave it out to keep the value")
        return self


class RefBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    name_de: str | None
    name_pl: str | None
    color: str
    icon_id: UUID = Field(description=ICON_ID_READ)
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class RefWithFactorCreate(RefBaseCreate):
    point_factor: float


class RefWithFactorUpdate(RefBaseUpdate):
    point_factor: float | None = None


class RefWithFactorRead(RefBaseRead):
    point_factor: float


# --- Tables with a scale (difficulty_level, difficulty_sport, rarity, visibility): they also have a rank ---

RANK_MAX = 1000   # the column is a smallint; a scale never needs more than a few dozen steps


class RefRankedCreate(RefWithFactorCreate):
    rank: int = Field(ge=0, le=RANK_MAX, description="Place on the scale; higher = harder, rarer or worse. Equal values are allowed.")


class RefRankedUpdate(RefWithFactorUpdate):
    rank: int | None = Field(None, ge=0, le=RANK_MAX, description="Place on the scale; higher = harder, rarer or worse.")


class RefRankedRead(RefWithFactorRead):
    rank: int


# --- Special cases ---

class SportTypeCreate(RefWithFactorCreate):
    name: str  # required + unique on this table


class DifficultySportCreate(RefRankedCreate):
    sport_type_id: UUID | None = None


class DifficultySportUpdate(RefRankedUpdate):
    sport_type_id: UUID | None = None


class DifficultySportRead(RefRankedRead):
    sport_type_id: UUID | None


class CompendiumTypeCreate(RefWithFactorCreate):
    is_collectable: bool = True


class CompendiumTypeUpdate(RefWithFactorUpdate):
    is_collectable: bool | None = None


class CompendiumTypeRead(RefWithFactorRead):
    is_collectable: bool


# --- Detail schemas: single GET with ?expand= (a link is only an ID unless the caller asks for it) ---

class RefBaseDetail(RefBaseRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class RefWithFactorDetail(RefWithFactorRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class RefRankedDetail(RefRankedRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class DifficultySportDetail(DifficultySportRead):
    sport_type: RefWithFactorDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")


class CompendiumTypeDetail(CompendiumTypeRead):
    created_by_user: ExpandedUser | None = Link("created_by")
