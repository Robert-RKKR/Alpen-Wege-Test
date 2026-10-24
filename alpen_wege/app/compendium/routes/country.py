from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.schemas.geo import geojson_to_wkt
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.management.utils.event_logger import log_created, log_updated, log_deleted
from app.core.utils.responses import ApiResponse, ok, ok_list
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryCreate, CountryRead, CountryUpdate
from app.core.utils.scope import apply_scope

router = APIRouter(prefix="/countries", tags=["Compendium - Country"])


@router.get("", response_model=ApiResponse[list[CountryRead]])
async def list_countries(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("country", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatCountry)
    count_stmt = apply_scope(count_stmt, CompendiumCatCountry, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatCountry).order_by(CompendiumCatCountry.name).limit(limit).offset(offset)
    stmt = apply_scope(stmt, CompendiumCatCountry, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ApiResponse[CountryRead], status_code=status.HTTP_201_CREATED)
async def create_country(
    body: CountryCreate,
    access: AccessContext = Depends(resource_access("country", "create")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    obj = CompendiumCatCountry(**data, created_by=access.user.id)
    db.add(obj)
    await db.flush()
    log_created(db, obj, access.user.id)
    await db.commit()
    await db.refresh(obj)
    return ok(obj, code=201, message="Created")


@router.get("/{country_id}", response_model=ApiResponse[CountryRead])
async def get_country(
    country_id: UUID,
    access: AccessContext = Depends(resource_access("country", "read")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    check_object_access(access, obj, not_found_msg="Country not found")
    return ok(obj)


@router.patch("/{country_id}", response_model=ApiResponse[CountryRead])
async def update_country(
    country_id: UUID,
    body: CountryUpdate,
    access: AccessContext = Depends(resource_access("country", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    check_object_access(access, obj, not_found_msg="Country not found")
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    old_values = {f: getattr(obj, f) for f in data}
    for field, value in data.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, data, access.user.id)
    await db.commit()
    await db.refresh(obj)
    return ok(obj)


@router.delete("/{country_id}", response_model=ApiResponse[None])
async def delete_country(
    country_id: UUID,
    access: AccessContext = Depends(resource_access("country", "delete")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    check_object_access(access, obj, not_found_msg="Country not found")
    log_deleted(db, obj, access.user.id)
    await db.delete(obj)
    await db.commit()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import countries from CSV",
    description=csv_upload_description(CompendiumCatCountry),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("country", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CompendiumCatCountry, access.user.id, db)
    return ok(result, code=201, message="Import complete")
