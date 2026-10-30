"""Which rows use an icon: every table that has an icon_id (the 20 reference tables, countries, regions)."""
from uuid import UUID

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.core.models import (
    CoreRefAchievementCategory, CoreRefAchievementScope, CoreRefAchievementType, CoreRefCompany, CoreRefCompendiumType,
    CoreRefDifficultyLevel, CoreRefDifficultySport, CoreRefGearType, CoreRefPointReason, CoreRefPostType, CoreRefRarity,
    CoreRefRegionType, CoreRefResourceType, CoreRefScheduleStatus, CoreRefSnowCondition, CoreRefSportType,
    CoreRefTrailCondition, CoreRefVisibility, CoreRefWaypointType, CoreRefWeatherCondition,
)

# the name shown in the "in use" message -> the model
ICON_USERS = {
    "country": CompendiumCatCountry,
    "region": CompendiumCatRegion,
    "achievement category": CoreRefAchievementCategory,
    "achievement scope": CoreRefAchievementScope,
    "achievement type": CoreRefAchievementType,
    "company": CoreRefCompany,
    "compendium type": CoreRefCompendiumType,
    "difficulty level": CoreRefDifficultyLevel,
    "difficulty sport": CoreRefDifficultySport,
    "gear type": CoreRefGearType,
    "point reason": CoreRefPointReason,
    "post type": CoreRefPostType,
    "rarity": CoreRefRarity,
    "region type": CoreRefRegionType,
    "resource type": CoreRefResourceType,
    "schedule status": CoreRefScheduleStatus,
    "snow condition": CoreRefSnowCondition,
    "sport type": CoreRefSportType,
    "trail condition": CoreRefTrailCondition,
    "visibility": CoreRefVisibility,
    "waypoint type": CoreRefWaypointType,
    "weather condition": CoreRefWeatherCondition,
}


async def icon_usage(db: AsyncSession, icon_id: UUID) -> dict[str, int]:
    # {"country": 3, "sport type": 1, ...}: how many rows of each table point to the icon
    parts = [select(literal(what).label("w"), func.count()).where(m.icon_id == icon_id) for what, m in ICON_USERS.items()]
    return {w: n for w, n in (await db.execute(union_all(*parts))).all()}
