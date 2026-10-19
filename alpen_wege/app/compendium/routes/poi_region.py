from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.core.utils.responses import ApiResponse, ok, ok_list
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.poi_region import PoiRegionCreate, PoiRegionRead, PoiRegionUpdate

router = APIRouter(prefix="/poi-regions", tags=["Compendium - POI Region"])

_EAGER = [
    selectinload(CompendiumM2mPoiRegion.poi),
    selectinload(CompendiumM2mPoiRegion.region),
]


def _apply_scope(stmt, model, access: AccessContext):
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)
        )
    return stmt


@router.get("", response_model=ApiResponse[list[PoiRegionRead]])
async def list_poi_regions(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("poi_region", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumM2mPoiRegion)
    count_stmt = _apply_scope(count_stmt, CompendiumM2mPoiRegion, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .options(*_EAGER)
        .order_by(CompendiumM2mPoiRegion.slot_position)
        .limit(limit).offset(offset)
    )
    stmt = _apply_scope(stmt, CompendiumM2mPoiRegion, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ApiResponse[PoiRegionRead], status_code=status.HTTP_201_CREATED)
async def create_poi_region(
    body: PoiRegionCreate,
    access: AccessContext = Depends(resource_access("poi_region", "create")),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumM2mPoiRegion(**body.model_dump(exclude_unset=True), created_by=access.user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")


@router.get("/{poi_region_id}", response_model=ApiResponse[PoiRegionRead])
async def get_poi_region(
    poi_region_id: UUID,
    access: AccessContext = Depends(resource_access("poi_region", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == poi_region_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="POI-Region link not found")
    return ok(obj)


@router.patch("/{poi_region_id}", response_model=ApiResponse[PoiRegionRead])
async def update_poi_region(
    poi_region_id: UUID,
    body: PoiRegionUpdate,
    access: AccessContext = Depends(resource_access("poi_region", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumM2mPoiRegion, poi_region_id)
    check_object_access(access, obj, not_found_msg="POI-Region link not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == poi_region_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one())


@router.delete("/{poi_region_id}", response_model=ApiResponse[None])
async def delete_poi_region(
    poi_region_id: UUID,
    access: AccessContext = Depends(resource_access("poi_region", "delete")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumM2mPoiRegion, poi_region_id)
    check_object_access(access, obj, not_found_msg="POI-Region link not found")
    await db.delete(obj)
    await db.commit()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import POI-region links from CSV",
    description=csv_upload_description(CompendiumM2mPoiRegion),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("poi_region", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CompendiumM2mPoiRegion, access.user.id, db)
    return ok(result, code=201, message="Import complete")
