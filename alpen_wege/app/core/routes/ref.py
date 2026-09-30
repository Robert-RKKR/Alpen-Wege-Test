from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
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


def _build_ref_router(*, model, create_schema, update_schema, read_schema, slug: str, tag: str = "ref") -> APIRouter:
    router = APIRouter(prefix=f"/{slug}", tags=[tag])

    @router.get("", response_model=list[read_schema])
    async def list_items(
        user: ProfileUsrUser = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        result = await db.execute(select(model).order_by(model.name))
        return result.scalars().all()

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    async def create_item(
        body: create_schema,
        user: ProfileUsrUser = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        obj = model(**body.model_dump(exclude_unset=True), created_by=user.id)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.get("/{item_id}", response_model=read_schema)
    async def get_item(
        item_id: UUID,
        user: ProfileUsrUser = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await db.get(model, item_id)
        if not obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{slug} not found")
        return obj

    @router.patch("/{item_id}", response_model=read_schema)
    async def update_item(
        item_id: UUID,
        body: update_schema,
        user: ProfileUsrUser = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await db.get(model, item_id)
        if not obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{slug} not found")
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_item(
        item_id: UUID,
        user: ProfileUsrUser = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await db.get(model, item_id)
        if not obj:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{slug} not found")
        await db.delete(obj)
        await db.commit()

    _desc = csv_upload_description(model)

    @router.post(
        "/upload-csv",
        response_model=CsvImportResult,
        summary=f"Import {slug} from CSV",
        description=_desc,
    )
    async def upload_csv(
        file: UploadFile = File(..., description="CSV file with header row"),
        user: ProfileUsrUser = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ):
        return await import_csv(file, model, user.id, db)

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
