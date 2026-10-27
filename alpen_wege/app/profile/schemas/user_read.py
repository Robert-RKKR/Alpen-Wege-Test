# Standard library
from datetime import date, datetime
from typing import ClassVar
from uuid import UUID

# Third-party
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


class UserExpandedRead(UserRead):
    # The user object in expanded responses (created_by, changed_by, updated_by, user). Everybody sees id and
    # username; the other fields are only for administrators and for the user himself, everybody else gets null.
    PUBLIC_FIELDS: ClassVar[tuple[str, ...]] = ("id", "username")

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    height_cm: int | None = None
    max_heart_rate: int | None = None
    resting_heart_rate: int | None = None
    is_active: bool | None = None
    created_at: datetime | None = None
    last_active_at: datetime | None = None

    @classmethod
    def redact(cls, data: dict, viewer) -> dict:
        # Called by ExpandPlan.render for every expanded user. No viewer means the safe answer: only the public fields.
        if viewer is not None and (viewer.id == data["id"] or viewer.user_group == "administrator"):
            return data
        return {name: (value if name in cls.PUBLIC_FIELDS else None) for name, value in data.items()}


# The user object that expanded responses return. One alias, so the rule "who sees which user fields" can be
# changed in one place.
ExpandedUser = UserExpandedRead
