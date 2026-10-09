# Standard library
from datetime import date

# Third-party
from pydantic import BaseModel, Field


class UserUpdate(BaseModel):
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    gender: str | None = Field(None, pattern=r"^(male|female|not_specified)$")
    birth_date: date | None = None
    height_cm: int | None = Field(None, ge=50, le=300)
    max_heart_rate: int | None = Field(None, ge=60, le=250)
    resting_heart_rate: int | None = Field(None, ge=20, le=150)
