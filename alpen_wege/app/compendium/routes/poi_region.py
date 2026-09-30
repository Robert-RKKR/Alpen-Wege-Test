from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.poi_region import PoiRegionCreate, PoiRegionRead, PoiRegionUpdate

router = APIRouter(prefix="/poi-regions", tags=["poi-regions"])

_EAGER = [
    selectinload(CompendiumM2mPoiRegion.poi),
    selectinload(CompendiumM2mPoiRegion.region),
]


@router.get("", response_model=list[PoiRegionRead])
async def list_poi_regions(
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumM2mPoiRegion)
        .options(*_EAGER)
        .order_by(CompendiumM2mPoiRegion.slot_position)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=PoiRegionRead, status_code=status.HTTP_201_CREATED)
async def create_poi_region(
    body: PoiRegionCreate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumM2mPoiRegion(**body.model_dump(exclude_unset=True), created_by=user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.get("/{poi_region_id}", response_model=PoiRegionRead)
async def get_poi_region(
    poi_region_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == poi_region_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "POI-Region link not found")
    return obj


@router.patch("/{poi_region_id}", response_model=PoiRegionRead)
async def update_poi_region(
    poi_region_id: UUID,
    body: PoiRegionUpdate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumM2mPoiRegion, poi_region_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "POI-Region link not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.id == poi_region_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.delete("/{poi_region_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_poi_region(
    poi_region_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumM2mPoiRegion, poi_region_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "POI-Region link not found")
    await db.delete(obj)
    await db.commit()


@router.post(
    "/upload-csv",
    response_model=CsvImportResult,
    summary="Import POI-region links from CSV",
    description=csv_upload_description(CompendiumM2mPoiRegion),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_csv(file, CompendiumM2mPoiRegion, user.id, db)
