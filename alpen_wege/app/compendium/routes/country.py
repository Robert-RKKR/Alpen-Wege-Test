from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.schemas.geo import geojson_to_wkt
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryCreate, CountryRead, CountryUpdate

router = APIRouter(prefix="/countries", tags=["countries"])


@router.get("", response_model=list[CountryRead])
async def list_countries(
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompendiumCatCountry).order_by(CompendiumCatCountry.name)
    )
    return result.scalars().all()


@router.post("", response_model=CountryRead, status_code=status.HTTP_201_CREATED)
async def create_country(
    body: CountryCreate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    obj = CompendiumCatCountry(**data, created_by=user.id)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/{country_id}", response_model=CountryRead)
async def get_country(
    country_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Country not found")
    return obj


@router.patch("/{country_id}", response_model=CountryRead)
async def update_country(
    country_id: UUID,
    body: CountryUpdate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Country not found")
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    for field, value in data.items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{country_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_country(
    country_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Country not found")
    await db.delete(obj)
    await db.commit()


@router.post(
    "/upload-csv",
    response_model=CsvImportResult,
    summary="Import countries from CSV",
    description=csv_upload_description(CompendiumCatCountry),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_csv(file, CompendiumCatCountry, user.id, db)
