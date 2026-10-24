# Standard library
from datetime import datetime
from typing import Literal

# Third-party
from pydantic import BaseModel, ConfigDict, Field


class BroadcastCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["info", "warning", "critical"] = "info"
    text: str = Field(min_length=1, max_length=500)
    expires_at: datetime | None = None


class BroadcastResult(BaseModel):
    delivered_to: int
