from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.management.utils.event_logger import log_created, log_updated, log_deleted
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.responses import ApiResponse, ok, ok_list
from app.explorer.schemas.gear import GearCreate, GearRead, GearUpdate
from app.core.utils.scope import apply_scope

router = APIRouter(prefix="/gear", tags=["Explorer - Gear"])


@router.get("", response_model=ApiResponse[list[GearRead]])
async def list_gear(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("gear", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(ExplorerAggGear)
    count_stmt = apply_scope(count_stmt, ExplorerAggGear, access)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(ExplorerAggGear)
        .order_by(ExplorerAggGear.created_at.desc())
        .limit(limit).offset(offset)
    )
    stmt = apply_scope(stmt, ExplorerAggGear, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ApiResponse[GearRead], status_code=status.HTTP_201_CREATED)
async def create_gear(
    body: GearCreate,
    access: AccessContext = Depends(resource_access("gear", "create")),
    db: AsyncSession = Depends(get_db),
):
    gear = ExplorerAggGear(
        **body.model_dump(exclude_unset=True),
        created_by=access.user.id,
    )
    db.add(gear)
    await db.flush()
    log_created(db, gear, access.user.id)
    await db.commit()
    await db.refresh(gear)
    return ok(gear, code=201, message="Created")


@router.get("/{gear_id}", response_model=ApiResponse[GearRead])
async def get_gear(
    gear_id: UUID,
    access: AccessContext = Depends(resource_access("gear", "read")),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    check_object_access(access, gear, not_found_msg="Gear not found")
    return ok(gear)


@router.patch("/{gear_id}", response_model=ApiResponse[GearRead])
async def update_gear(
    gear_id: UUID,
    body: GearUpdate,
    access: AccessContext = Depends(resource_access("gear", "update")),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    check_object_access(access, gear, not_found_msg="Gear not found")
    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(gear, f) for f in changes}
    for field, value in changes.items():
        setattr(gear, field, value)
    log_updated(db, gear, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(gear)
    return ok(gear)


@router.delete("/{gear_id}", response_model=ApiResponse[None])
async def delete_gear(
    gear_id: UUID,
    access: AccessContext = Depends(resource_access("gear", "delete")),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    check_object_access(access, gear, not_found_msg="Gear not found")
    log_deleted(db, gear, access.user.id)
    await db.delete(gear)
    await db.commit()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import gear from CSV",
    description=csv_upload_description(ExplorerAggGear),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("gear", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, ExplorerAggGear, access.user.id, db)
    return ok(result, code=201, message="Import complete")
