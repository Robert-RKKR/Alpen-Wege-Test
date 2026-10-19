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
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.schemas.poi import PoiCreate, PoiRead, PoiUpdate

router = APIRouter(prefix="/pois", tags=["Compendium - POI"])

_EAGER = [
    selectinload(CompendiumCatPoi.compendium_type),
    selectinload(CompendiumCatPoi.main_region),
]


def _apply_scope(stmt, model, access: AccessContext):
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)
        )
    return stmt


@router.get("", response_model=ApiResponse[list[PoiRead]])
async def list_pois(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("poi", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatPoi)
    count_stmt = _apply_scope(count_stmt, CompendiumCatPoi, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatPoi).options(*_EAGER).order_by(CompendiumCatPoi.name).limit(limit).offset(offset)
    stmt = _apply_scope(stmt, CompendiumCatPoi, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ApiResponse[PoiRead], status_code=status.HTTP_201_CREATED)
async def create_poi(
    body: PoiCreate,
    access: AccessContext = Depends(resource_access("poi", "create")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    obj = CompendiumCatPoi(**data, created_by=access.user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")


@router.get("/{poi_id}", response_model=ApiResponse[PoiRead])
async def get_poi(
    poi_id: UUID,
    access: AccessContext = Depends(resource_access("poi", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == poi_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="POI not found")
    return ok(obj)


@router.patch("/{poi_id}", response_model=ApiResponse[PoiRead])
async def update_poi(
    poi_id: UUID,
    body: PoiUpdate,
    access: AccessContext = Depends(resource_access("poi", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPoi, poi_id)
    check_object_access(access, obj, not_found_msg="POI not found")
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
    return ok(result.scalar_one())


@router.delete("/{poi_id}", response_model=ApiResponse[None])
async def delete_poi(
    poi_id: UUID,
    access: AccessContext = Depends(resource_access("poi", "delete")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPoi, poi_id)
    check_object_access(access, obj, not_found_msg="POI not found")
    await db.delete(obj)
    await db.commit()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import POIs from CSV",
    description=csv_upload_description(CompendiumCatPoi),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("poi", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CompendiumCatPoi, access.user.id, db)
    return ok(result, code=201, message="Import complete")
