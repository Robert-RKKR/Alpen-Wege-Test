# Standard library
from datetime import datetime
from uuid import UUID

# Third-party
from pydantic import BaseModel, ConfigDict


# --- Resource Type ---


class ResourceTypeCreate(BaseModel):
    key: str
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str
    icon: str


class ResourceTypeUpdate(BaseModel):
    key: str | None = None
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str | None = None
    icon: str | None = None


class ResourceTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str | None
    name_de: str | None
    name_pl: str | None
    color: str
    icon: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime


# --- Access Policy ---


class AccessPolicyCreate(BaseModel):
    user_group: str
    resource_type_id: UUID
    action: str
    scope: str


class AccessPolicyUpdate(BaseModel):
    scope: str


class AccessPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_group: str
    resource_type_id: UUID
    action: str
    scope: str
    created_at: datetime
    updated_at: datetime


class AccessPolicyReadWithKey(AccessPolicyRead):
    resource_key: str | None = None
