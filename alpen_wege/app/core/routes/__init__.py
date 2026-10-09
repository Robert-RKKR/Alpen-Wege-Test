from fastapi import APIRouter

from .ref import routers as ref_routers

router = APIRouter(prefix="/ref")
for r in ref_routers:
    router.include_router(r)
