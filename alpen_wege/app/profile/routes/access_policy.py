# Standard library
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
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
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import (
    AccessPolicyCreate,
    AccessPolicyRead,
    AccessPolicyReadWithKey,
    AccessPolicyUpdate,
)
from app.profile.models import ProfileUsrUser


router = APIRouter(prefix="/access-policies", tags=["Auth", "Auth - Access Policies"])


@router.get("", response_model=ApiResponse[list[AccessPolicyReadWithKey]])
async def list_access_policies(
    limit: int = 1000,
    offset: int = 0,
    group: str | None = Query(None),
    resource_key: str | None = Query(None),
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    base = select(ProfileAccessPolicy).join(CoreRefResourceType)
    count_base = select(func.count()).select_from(ProfileAccessPolicy).join(CoreRefResourceType)

    if group:
        base = base.where(ProfileAccessPolicy.user_group == group)
        count_base = count_base.where(ProfileAccessPolicy.user_group == group)
    if resource_key:
        base = base.where(CoreRefResourceType.key == resource_key)
        count_base = count_base.where(CoreRefResourceType.key == resource_key)

    total = (await db.execute(count_base)).scalar()
    stmt = (
        base
        .order_by(ProfileAccessPolicy.user_group, CoreRefResourceType.key, ProfileAccessPolicy.action)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items = []
    for row in rows:
        data = {
            "id": row.id,
            "user_group": row.user_group,
            "resource_type_id": row.resource_type_id,
            "action": row.action,
            "scope": row.scope,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "resource_key": row.resource_type.key if row.resource_type else None,
        }
        items.append(AccessPolicyReadWithKey(**data))

    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=ApiResponse[AccessPolicyRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_access_policy(
    body: AccessPolicyCreate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    rt = await db.get(CoreRefResourceType, body.resource_type_id)
    if not rt:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="The referenced resource type does not exist.",
            error_errors=[{"field": "resource_type_id", "code": "not_found", "message": "Resource type does not exist"}],
        )

    existing = await db.execute(
        select(ProfileAccessPolicy).where(
            ProfileAccessPolicy.user_group == body.user_group,
            ProfileAccessPolicy.resource_type_id == body.resource_type_id,
            ProfileAccessPolicy.action == body.action,
        )
    )
    if existing.scalar_one_or_none():
        raise AppError(
            status.HTTP_409_CONFLICT,
            "Duplicate entry",
            error_message="An access policy for this combination already exists.",
            error_errors=[{"field": "user_group+resource_type_id+action", "code": "conflict", "message": "Policy combination already exists"}],
        )

    obj = ProfileAccessPolicy(**body.model_dump())
    db.add(obj)
    await db.flush()
    log_created(db, obj, admin.id)
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache(body.user_group, rt.key)
    return ok(obj, code=201, message="Created")


@router.get("/{item_id}", response_model=ApiResponse[AccessPolicyRead])
async def get_access_policy(
    item_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(ProfileAccessPolicy, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No access policy exists with the given ID.",
        )
    return ok(obj)


@router.patch("/{item_id}", response_model=ApiResponse[AccessPolicyRead])
async def update_access_policy(
    item_id: UUID,
    body: AccessPolicyUpdate,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(ProfileAccessPolicy, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No access policy exists with the given ID.",
        )
    old_values = {"scope": obj.scope}
    obj.scope = body.scope
    log_updated(db, obj, old_values, {"scope": body.scope}, admin.id)
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache()
    return ok(obj)


@router.delete("/{item_id}", response_model=ApiResponse[None])
async def delete_access_policy(
    item_id: UUID,
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(ProfileAccessPolicy, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No access policy exists with the given ID.",
        )
    log_deleted(db, obj, admin.id)
    await db.delete(obj)
    await db.commit()
    await invalidate_policy_cache()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import access policies from CSV",
    description=csv_upload_description(ProfileAccessPolicy),
)
async def upload_access_policy_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, ProfileAccessPolicy, admin.id, db)
    await invalidate_policy_cache()
    return ok(result, code=201, message="Import complete")
