# Standard library
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created, log_updated, log_deleted
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.profile.permissions import require_groups
from app.profile.services.access_cache import invalidate_policy_cache
from app.core.models.resource_type import CoreRefResourceType
from app.profile.schemas.access_policy import (
    ResourceTypeCreate,
    ResourceTypeRead,
    ResourceTypeUpdate,
)
from app.profile.models import ProfileUsrUser


router = APIRouter(prefix="/resource-types", tags=["Auth", "Auth - Resource Types"])


@router.get("", response_model=ApiResponse[list[ResourceTypeRead]])
async def list_resource_types(
    limit: int = 1000,
    offset: int = 0,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(CoreRefResourceType))).scalar()
    stmt = (
        select(CoreRefResourceType)
        .order_by(CoreRefResourceType.key)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return ok_list(result.scalars().all(), total=total, limit=limit, offset=offset)


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


@router.get("/{item_id}", response_model=ApiResponse[ResourceTypeRead])
async def get_resource_type(
    item_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CoreRefResourceType, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No resource type exists with the given ID.",
        )
    return ok(obj)


@router.patch("/{item_id}", response_model=ApiResponse[ResourceTypeRead])
async def update_resource_type(
    item_id: UUID,
    body: ResourceTypeUpdate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CoreRefResourceType, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No resource type exists with the given ID.",
        )
    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(obj, f) for f in changes}
    for field, value in changes.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, changes, admin.id)
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache()
    return ok(obj)


@router.delete("/{item_id}", response_model=ApiResponse[None])
async def delete_resource_type(
    item_id: UUID,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CoreRefResourceType, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No resource type exists with the given ID.",
        )
    log_deleted(db, obj, admin.id)
    await db.delete(obj)
    await db.commit()
    await invalidate_policy_cache()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import resource types from CSV",
    description=csv_upload_description(CoreRefResourceType),
)
async def upload_resource_type_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CoreRefResourceType, admin.id, db)
    return ok(result, code=201, message="Import complete")
