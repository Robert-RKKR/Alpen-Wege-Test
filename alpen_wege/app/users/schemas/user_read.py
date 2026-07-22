from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    first_name: str | None
    last_name: str | None
    middle_name: str | None
    gender: str | None
    birth_date: date | None
    height_cm: int | None
    max_heart_rate: int | None
    resting_heart_rate: int | None
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    user_group: str | None = None
