from fastapi import APIRouter

from .gear import router as gear_router

router = APIRouter()
router.include_router(gear_router)
