from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.core.utils.responses import ApiResponse, ok, ok_list
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.core.models.models_ref import (
    CoreRefAchievementCategory,
    CoreRefAchievementScope,
    CoreRefAchievementType,
    CoreRefCompany,
    CoreRefCompendiumType,
    CoreRefDifficultyLevel,
    CoreRefDifficultySport,
    CoreRefGearType,
    CoreRefPointReason,
    CoreRefPostType,
    CoreRefRarity,
    CoreRefRegionType,
    CoreRefScheduleStatus,
    CoreRefSnowCondition,
    CoreRefSportType,
    CoreRefTrailCondition,
    CoreRefVisibility,
    CoreRefWaypointType,
    CoreRefWeatherCondition,
)
from app.core.schemas.ref import (
    RefBaseCreate,
    RefBaseUpdate,
    RefBaseRead,
    RefWithFactorCreate,
    RefWithFactorUpdate,
    RefWithFactorRead,
    SportTypeCreate,
    DifficultySportCreate,
    DifficultySportUpdate,
    DifficultySportRead,
)


def _build_ref_router(
    *,
    model,
    create_schema,
    update_schema,
    read_schema,
    slug: str,
    resource_key: str = "ref",
) -> APIRouter:
    tag = f"Reference - {slug.replace('-', ' ').title()}"
    router = APIRouter(prefix=f"/{slug}", tags=[tag])

    @router.get("", response_model=ApiResponse[list[read_schema]])
    async def list_items(
        limit: int = 1000,
        offset: int = 0,
        access: AccessContext = Depends(resource_access(resource_key, "read")),
        db: AsyncSession = Depends(get_db),
    ):
        count_stmt = select(func.count()).select_from(model)
        if access.scope == "own":
            count_stmt = count_stmt.where(model.created_by == access.user.id)
        total = (await db.execute(count_stmt)).scalar()

        stmt = select(model).order_by(model.name).limit(limit).offset(offset)
        if access.scope == "own":
            stmt = stmt.where(model.created_by == access.user.id)
        result = await db.execute(stmt)
        return ok_list(result.scalars().all(), total=total, limit=limit, offset=offset)

    @router.post("", response_model=ApiResponse[read_schema], status_code=status.HTTP_201_CREATED)
    async def create_item(
        body: create_schema,
        access: AccessContext = Depends(resource_access(resource_key, "create")),
        db: AsyncSession = Depends(get_db),
    ):
        obj = model(**body.model_dump(exclude_unset=True), created_by=access.user.id)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return ok(obj, code=201, message="Created")

    @router.get("/{item_id}", response_model=ApiResponse[read_schema])
    async def get_item(
        item_id: UUID,
        access: AccessContext = Depends(resource_access(resource_key, "read")),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await db.get(model, item_id)
        check_object_access(access, obj, not_found_msg=f"{slug} not found")
        return ok(obj)

    @router.patch("/{item_id}", response_model=ApiResponse[read_schema])
    async def update_item(
        item_id: UUID,
        body: update_schema,
        access: AccessContext = Depends(resource_access(resource_key, "update")),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await db.get(model, item_id)
        check_object_access(access, obj, not_found_msg=f"{slug} not found")
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await db.commit()
        await db.refresh(obj)
        return ok(obj)

    @router.delete("/{item_id}", response_model=ApiResponse[None])
    async def delete_item(
        item_id: UUID,
        access: AccessContext = Depends(resource_access(resource_key, "delete")),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await db.get(model, item_id)
        check_object_access(access, obj, not_found_msg=f"{slug} not found")
        await db.delete(obj)
        await db.commit()
        return ok(None, message="Deleted")

    _desc = csv_upload_description(model)

    @router.post(
        "/upload-csv",
        response_model=ApiResponse[CsvImportResult],
        summary=f"Import {slug} from CSV",
        description=_desc,
    )
    async def upload_csv(
        file: UploadFile = File(..., description="CSV file with header row"),
        access: AccessContext = Depends(resource_access(resource_key, "create")),
        db: AsyncSession = Depends(get_db),
    ):
        result = await import_csv(file, model, access.user.id, db)
        return ok(result, code=201, message="Import complete")

    return router


# --- Register all 19 core_ref tables ---

_BASE_TABLES = [
    (CoreRefCompany, "companies"),
    (CoreRefGearType, "gear-types"),
]

_FACTOR_TABLES = [
    (CoreRefAchievementCategory, "achievement-categories"),
    (CoreRefAchievementScope, "achievement-scopes"),
    (CoreRefAchievementType, "achievement-types"),
    (CoreRefCompendiumType, "compendium-types"),
    (CoreRefDifficultyLevel, "difficulty-levels"),
    (CoreRefPointReason, "point-reasons"),
    (CoreRefPostType, "post-types"),
    (CoreRefRarity, "rarities"),
    (CoreRefRegionType, "region-types"),
    (CoreRefScheduleStatus, "schedule-statuses"),
    (CoreRefSnowCondition, "snow-conditions"),
    (CoreRefTrailCondition, "trail-conditions"),
    (CoreRefVisibility, "visibilities"),
    (CoreRefWaypointType, "waypoint-types"),
    (CoreRefWeatherCondition, "weather-conditions"),
]

routers: list[APIRouter] = []

for model, slug in _BASE_TABLES:
    routers.append(_build_ref_router(
        model=model, create_schema=RefBaseCreate, update_schema=RefBaseUpdate,
        read_schema=RefBaseRead, slug=slug,
    ))

for model, slug in _FACTOR_TABLES:
    routers.append(_build_ref_router(
        model=model, create_schema=RefWithFactorCreate, update_schema=RefWithFactorUpdate,
        read_schema=RefWithFactorRead, slug=slug,
    ))

# Special: SportType (name required)
routers.append(_build_ref_router(
    model=CoreRefSportType, create_schema=SportTypeCreate,
    update_schema=RefWithFactorUpdate, read_schema=RefWithFactorRead,
    slug="sport-types",
))

# Special: DifficultySport (+ sport_type_id)
routers.append(_build_ref_router(
    model=CoreRefDifficultySport, create_schema=DifficultySportCreate,
    update_schema=DifficultySportUpdate, read_schema=DifficultySportRead,
    slug="difficulty-sports",
))
