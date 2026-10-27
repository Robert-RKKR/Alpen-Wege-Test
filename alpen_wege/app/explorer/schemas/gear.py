from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser
from app.core.schemas.ref import RefBaseDetail


class GearCreate(BaseModel):
    name: str
    company_id: UUID
    gear_type_id: UUID
    model: str | None = None
    weight_g: int | None = None
    summary: str | None = None
    description: str | None = None


class GearUpdate(BaseModel):
    name: str | None = None
    company_id: UUID | None = None
    gear_type_id: UUID | None = None
    model: str | None = None
    weight_g: int | None = None
    summary: str | None = None
    description: str | None = None


class GearRead(BaseModel):
    id: UUID
    name: str
    company_id: UUID
    gear_type_id: UUID
    model: str | None
    weight_g: int | None
    summary: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GearDetail(GearRead):
    company: RefBaseDetail | None = Link()
    gear_type: RefBaseDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
