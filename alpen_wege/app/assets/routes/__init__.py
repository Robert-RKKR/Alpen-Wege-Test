from fastapi import APIRouter

from .gpx import router as gpx_router
from .icon import router as icon_router
from .photo import router as photo_router

router = APIRouter(prefix="/assets")
router.include_router(photo_router)
router.include_router(gpx_router)
router.include_router(icon_router)
