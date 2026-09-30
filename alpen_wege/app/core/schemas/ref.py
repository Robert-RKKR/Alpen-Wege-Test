from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RefBaseCreate(BaseModel):
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str
    icon: str


class RefBaseUpdate(BaseModel):
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str | None = None
    icon: str | None = None


class RefBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    name_de: str | None
    name_pl: str | None
    color: str
    icon: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class RefWithFactorCreate(RefBaseCreate):
    point_factor: float


class RefWithFactorUpdate(RefBaseUpdate):
    point_factor: float | None = None


class RefWithFactorRead(RefBaseRead):
    point_factor: float


# --- Special cases ---

class SportTypeCreate(RefWithFactorCreate):
    name: str  # required + unique on this table


class DifficultySportCreate(RefWithFactorCreate):
    sport_type_id: UUID | None = None


class DifficultySportUpdate(RefWithFactorUpdate):
    sport_type_id: UUID | None = None


class DifficultySportRead(RefWithFactorRead):
    sport_type_id: UUID | None
