# Standard library
from datetime import datetime
from typing import Any
from uuid import UUID

# Third-party
from pydantic import BaseModel, ConfigDict


class SettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any
    value_type: str
    default_value: Any
    min_value: float | None = None
    max_value: float | None = None
    category: str
    description: str
    requires_restart: bool
    updated_at: datetime
    updated_by: UUID | None = None


class SettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
