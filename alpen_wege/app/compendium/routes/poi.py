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
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.schemas.poi import PoiCreate, PoiRead, PoiUpdate

router = APIRouter(prefix="/pois", tags=["pois"])

_EAGER = [
    selectinload(CompendiumCatPoi.compendium_type),
    selectinload(CompendiumCatPoi.main_region),
]


@router.get("", response_model=list[PoiRead])
async def list_pois(
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CompendiumCatPoi).options(*_EAGER).order_by(CompendiumCatPoi.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=PoiRead, status_code=status.HTTP_201_CREATED)
async def create_poi(
    body: PoiCreate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    obj = CompendiumCatPoi(**data, created_by=user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.get("/{poi_id}", response_model=PoiRead)
async def get_poi(
    poi_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == poi_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "POI not found")
    return obj


@router.patch("/{poi_id}", response_model=PoiRead)
async def update_poi(
    poi_id: UUID,
    body: PoiUpdate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPoi, poi_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "POI not found")
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    for field, value in data.items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == poi_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.delete("/{poi_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_poi(
    poi_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPoi, poi_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "POI not found")
    await db.delete(obj)
    await db.commit()


@router.post(
    "/upload-csv",
    response_model=CsvImportResult,
    summary="Import POIs from CSV",
    description=csv_upload_description(CompendiumCatPoi),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_csv(file, CompendiumCatPoi, user.id, db)
