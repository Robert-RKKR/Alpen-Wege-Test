from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.schemas.geo import geojson_to_wkt
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionCreate, RegionRead, RegionUpdate

router = APIRouter(prefix="/regions", tags=["regions"])

_EAGER = [
    selectinload(CompendiumCatRegion.country),
    selectinload(CompendiumCatRegion.region_type),
    selectinload(CompendiumCatRegion.parent),
]


@router.get("", response_model=list[RegionRead])
async def list_regions(
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CompendiumCatRegion).options(*_EAGER).order_by(CompendiumCatRegion.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=RegionRead, status_code=status.HTTP_201_CREATED)
async def create_region(
    body: RegionCreate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    if "bbox" in data:
        data["bbox"] = geojson_to_wkt(data["bbox"], "POLYGON")
    obj = CompendiumCatRegion(**data, created_by=user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.get("/{region_id}", response_model=RegionRead)
async def get_region(
    region_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatRegion)
        .where(CompendiumCatRegion.id == region_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found")
    return obj


@router.patch("/{region_id}", response_model=RegionRead)
async def update_region(
    region_id: UUID,
    body: RegionUpdate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatRegion, region_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found")
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
    return result.scalar_one()


@router.delete("/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_region(
    region_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatRegion, region_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found")
    await db.delete(obj)
    await db.commit()


@router.post(
    "/upload-csv",
    response_model=CsvImportResult,
    summary="Import regions from CSV",
    description=csv_upload_description(CompendiumCatRegion),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_csv(file, CompendiumCatRegion, user.id, db)
