from fastapi import APIRouter

from . import resource_type
from .ref import router as ref_router

router = APIRouter(prefix="/core")
router.include_router(ref_router)
router.include_router(resource_type.router)
