# Standard library
from datetime import datetime
from uuid import UUID

# Third-party
from pydantic import BaseModel, ConfigDict, Field

from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser


# --- Resource Type ---

ICON_ID_WRITE = "Link to the picture of this resource type: the id of an icon (`GET /assets/icons`, an SVG). Optional. An unknown id answers 422. The text in `icon` stays as it is."


class ResourceTypeCreate(BaseModel):
    key: str
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str
    icon: str
    icon_id: UUID | None = Field(None, description=ICON_ID_WRITE)


class ResourceTypeUpdate(BaseModel):
    key: str | None = None
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    color: str | None = None
    icon: str | None = None
    icon_id: UUID | None = Field(None, description=ICON_ID_WRITE + " `null` removes the link; leave the field out to keep it.")


class ResourceTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str | None
    name_de: str | None
    name_pl: str | None
    color: str
    icon: str
    icon_id: UUID | None = Field(description="Id of the icon (an SVG) of this resource type, or null. The picture: `GET /assets/icons/{icon_id}/file`.")
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class ResourceTypeDetail(ResourceTypeRead):
    created_by_user: ExpandedUser | None = Link("created_by")


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


class AccessPolicyDetail(AccessPolicyRead):
    resource_type: ResourceTypeDetail | None = Link()


class AccessPolicyReadWithKey(AccessPolicyRead):
    resource_key: str | None = None
