# Third-party
from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.core.models.resource_type import CoreRefResourceType
from app.profile.schemas.access_policy import (
    ResourceTypeCreate,
    ResourceTypeRead,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.post(
    "",
    response_model=ApiResponse[ResourceTypeRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_resource_type(
    body: ResourceTypeCreate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(CoreRefResourceType).where(CoreRefResourceType.key == body.key)
    )
    if existing.scalar_one_or_none():
        raise AppError(
            status.HTTP_409_CONFLICT,
            "Duplicate entry",
            error_message="A resource type with this key already exists.",
            error_errors=[{"field": "key", "code": "conflict", "message": "Key already in use"}],
        )
    obj = CoreRefResourceType(**body.model_dump(exclude_unset=True), created_by=admin.id)
    db.add(obj)
    await db.flush()
    log_created(db, obj, admin.id)
    await db.commit()
    await db.refresh(obj)
    return ok(obj, code=201, message="Created")
