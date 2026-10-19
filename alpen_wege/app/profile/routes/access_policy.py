# Standard library
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.profile.permissions import require_groups
from app.profile.services.access_cache import invalidate_policy_cache
from app.core.models.resource_type import CoreRefResourceType
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import (
    ResourceTypeCreate,
    ResourceTypeRead,
    ResourceTypeUpdate,
    AccessPolicyCreate,
    AccessPolicyRead,
    AccessPolicyReadWithKey,
    AccessPolicyUpdate,
)
from app.profile.models import ProfileUsrUser


# ============================================================
# Resource Types — /api/v1/auth/resource-types
# ============================================================

resource_type_router = APIRouter(
    prefix="/resource-types",
    tags=["Auth - Resource Types"],
)


@resource_type_router.get("", response_model=ApiResponse[list[ResourceTypeRead]])
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


@resource_type_router.post(
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
    await db.commit()
    await db.refresh(obj)
    return ok(obj, code=201, message="Created")


@resource_type_router.get("/{item_id}", response_model=ApiResponse[ResourceTypeRead])
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


@resource_type_router.patch("/{item_id}", response_model=ApiResponse[ResourceTypeRead])
async def update_resource_type(
    item_id: UUID,
    body: ResourceTypeUpdate,
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
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache()
    return ok(obj)


@resource_type_router.delete("/{item_id}", response_model=ApiResponse[None])
async def delete_resource_type(
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
    await db.delete(obj)
    await db.commit()
    await invalidate_policy_cache()
    return ok(None, message="Deleted")


@resource_type_router.post(
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


# ============================================================
# Access Policies — /api/v1/auth/access-policies
# ============================================================

access_policy_router = APIRouter(
    prefix="/access-policies",
    tags=["Auth - Access Policies"],
)


@access_policy_router.get("", response_model=ApiResponse[list[AccessPolicyReadWithKey]])
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


@access_policy_router.post(
    "",
    response_model=ApiResponse[AccessPolicyRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_access_policy(
    body: AccessPolicyCreate,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
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
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache(body.user_group, rt.key)
    return ok(obj, code=201, message="Created")


@access_policy_router.get("/{item_id}", response_model=ApiResponse[AccessPolicyRead])
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


@access_policy_router.patch("/{item_id}", response_model=ApiResponse[AccessPolicyRead])
async def update_access_policy(
    item_id: UUID,
    body: AccessPolicyUpdate,
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
    obj.scope = body.scope
    await db.commit()
    await db.refresh(obj)
    await invalidate_policy_cache()
    return ok(obj)


@access_policy_router.delete("/{item_id}", response_model=ApiResponse[None])
async def delete_access_policy(
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
    await db.delete(obj)
    await db.commit()
    await invalidate_policy_cache()
    return ok(None, message="Deleted")


@access_policy_router.post(
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
