from fastapi import APIRouter

from .me import router as me_router
from .admin import router as admin_router

router = APIRouter(prefix="/users", tags=["users"])
router.include_router(me_router)
router.include_router(admin_router)
