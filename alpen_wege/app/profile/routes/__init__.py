from fastapi import APIRouter

from .register import router as register_router
from .login import router as login_router
from .refresh import router as refresh_router
from .logout import router as logout_router
from .access_policy import resource_type_router, access_policy_router
from .me import router as me_router
from .admin import router as admin_router

auth_router = APIRouter(prefix="/auth", tags=["Auth"])
auth_router.include_router(register_router)
auth_router.include_router(login_router)
auth_router.include_router(refresh_router)
auth_router.include_router(logout_router)
auth_router.include_router(resource_type_router)
auth_router.include_router(access_policy_router)

users_router = APIRouter(prefix="/users", tags=["Users"])
users_router.include_router(me_router)
users_router.include_router(admin_router)
