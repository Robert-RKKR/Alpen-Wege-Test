from fastapi import APIRouter

from .gear import router as gear_router
from .track import router as track_router

router = APIRouter(prefix="/explorer")
router.include_router(gear_router)
router.include_router(track_router)
