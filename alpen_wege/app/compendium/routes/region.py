from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok, ok_list
from app.core.schemas.geo import geojson_to_wkt
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionCreate, RegionRead, RegionUpdate

router = APIRouter(prefix="/regions", tags=["Compendium - Region"])

_EAGER = [
    selectinload(CompendiumCatRegion.country),
    selectinload(CompendiumCatRegion.region_type),
    selectinload(CompendiumCatRegion.parent),
]


def _apply_scope(stmt, model, access: AccessContext):
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)
        )
    return stmt


@router.get("", response_model=ApiResponse[list[RegionRead]])
async def list_regions(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("region", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatRegion)
    count_stmt = _apply_scope(count_stmt, CompendiumCatRegion, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatRegion).options(*_EAGER).order_by(CompendiumCatRegion.name).limit(limit).offset(offset)
    stmt = _apply_scope(stmt, CompendiumCatRegion, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ApiResponse[RegionRead], status_code=status.HTTP_201_CREATED)
async def create_region(
    body: RegionCreate,
    access: AccessContext = Depends(resource_access("region", "create")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    if "bbox" in data:
        data["bbox"] = geojson_to_wkt(data["bbox"], "POLYGON")
    obj = CompendiumCatRegion(**data, created_by=access.user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")


@router.get("/{region_id}", response_model=ApiResponse[RegionRead])
async def get_region(
    region_id: UUID,
    access: AccessContext = Depends(resource_access("region", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == region_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Region not found")
    return ok(obj)


@router.patch("/{region_id}", response_model=ApiResponse[RegionRead])
async def update_region(
    region_id: UUID,
    body: RegionUpdate,
    access: AccessContext = Depends(resource_access("region", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatRegion, region_id)
    check_object_access(access, obj, not_found_msg="Region not found")
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    if "bbox" in data:
        data["bbox"] = geojson_to_wkt(data["bbox"], "POLYGON")
    for field, value in data.items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == region_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one())


@router.delete("/{region_id}", response_model=ApiResponse[None])
async def delete_region(
    region_id: UUID,
    access: AccessContext = Depends(resource_access("region", "delete")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatRegion, region_id)
    check_object_access(access, obj, not_found_msg="Region not found")
    await db.delete(obj)
    await db.commit()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import regions from CSV",
    description=csv_upload_description(CompendiumCatRegion),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("region", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CompendiumCatRegion, access.user.id, db)
    return ok(result, code=201, message="Import complete")
