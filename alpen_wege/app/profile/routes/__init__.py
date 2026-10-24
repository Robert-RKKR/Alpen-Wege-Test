from fastapi import APIRouter

from . import access_policy
from .auth import router as auth_router
from .user import router as user_router

router = APIRouter(prefix="/profile")
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(access_policy.router)
