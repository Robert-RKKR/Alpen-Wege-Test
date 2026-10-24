# Standard library
from datetime import datetime
from typing import Any
from uuid import UUID

# Third-party
from pydantic import BaseModel, Field


class EntityTypeRead(BaseModel):
    id: UUID
    key: str
    display_name: str
    module: str
    tracking_mode: str
    ignore_fields: list[str] | None

    model_config = {"from_attributes": True}


class EventLogRead(BaseModel):
    id: UUID
    seq: int
    entity_type_id: UUID
    entity_type: EntityTypeRead
    entity_id: UUID
    action: str
    snapshot: dict
    changed_by: UUID
    changed_at: datetime
    request_id: str | None

    model_config = {"from_attributes": True}


class CompareEntryRef(BaseModel):
    id: UUID
    seq: int
    action: str
    changed_by: UUID
    changed_at: datetime
    request_id: str | None


class FieldChange(BaseModel):
    from_value: Any = Field(alias="from")
    to_value: Any = Field(alias="to")

    model_config = {"populate_by_name": True}


class EventLogCompare(BaseModel):
    entity_type: EntityTypeRead
    entity_id: UUID
    older: CompareEntryRef
    newer: CompareEntryRef
    events_between: int
    changes: dict[str, FieldChange]
    warnings: list[str] = []
