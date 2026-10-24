from fastapi import APIRouter

from . import poi_region

router = APIRouter()
router.include_router(poi_region.router)
