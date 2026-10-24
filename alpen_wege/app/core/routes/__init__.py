from fastapi import APIRouter

from .ref import router as ref_router

router = APIRouter(prefix="/core")
router.include_router(ref_router)
