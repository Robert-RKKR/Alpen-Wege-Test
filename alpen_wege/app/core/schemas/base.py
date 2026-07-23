# Standard library
from datetime import datetime
from uuid import UUID

# Third-party
from pydantic import BaseModel, ConfigDict


class UUIDModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
