# Third-party
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(
        min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$"
    )
    password: str = Field(min_length=8)
    first_name: str | None = None
    last_name: str | None = None
