from fastapi import APIRouter

from . import (
    company,
    gear_type,
    achievement_category,
    achievement_scope,
    achievement_type,
    difficulty_level,
    point_reason,
    post_type,
    rarity,
    region_type,
    schedule_status,
    snow_condition,
    trail_condition,
    visibility,
    waypoint_type,
    weather_condition,
    sport_type,
    difficulty_sport,
    compendium_type,
)

router = APIRouter()
router.include_router(company.router)
router.include_router(gear_type.router)
router.include_router(achievement_category.router)
router.include_router(achievement_scope.router)
router.include_router(achievement_type.router)
router.include_router(difficulty_level.router)
router.include_router(point_reason.router)
router.include_router(post_type.router)
router.include_router(rarity.router)
router.include_router(region_type.router)
router.include_router(schedule_status.router)
router.include_router(snow_condition.router)
router.include_router(trail_condition.router)
router.include_router(visibility.router)
router.include_router(waypoint_type.router)
router.include_router(weather_condition.router)
router.include_router(sport_type.router)
router.include_router(difficulty_sport.router)
router.include_router(compendium_type.router)
