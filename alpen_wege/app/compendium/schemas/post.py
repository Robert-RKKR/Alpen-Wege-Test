from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.schemas.ref import RefWithFactorRead


class PostCreate(BaseModel):
    name: str
    post_type_id: UUID
    main_photo_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class PostUpdate(BaseModel):
    name: str | None = None
    post_type_id: UUID | None = None
    main_photo_id: UUID | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    post_type_id: UUID
    post_type: RefWithFactorRead | None = None
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
