from fastapi import APIRouter

from .gear import router as gear_router
from .route import router as route_router
from .segment import router as segment_router
from .track import router as track_router

router = APIRouter(prefix="/explorer")
router.include_router(gear_router)
router.include_router(track_router)
router.include_router(segment_router)
router.include_router(route_router)
