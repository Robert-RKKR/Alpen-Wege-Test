from pydantic import BaseModel, Field


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None


class AdminGroupUpdate(BaseModel):
    user_group: str = Field(pattern=r"^(admin|editor|user)$")
