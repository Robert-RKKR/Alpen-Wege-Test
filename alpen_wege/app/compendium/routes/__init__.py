from fastapi import APIRouter

from .country import router as country_router
from .region import router as region_router
from .poi import router as poi_router
from .card import router as card_router
from .post import router as post_router
from .m2m import router as m2m_router

router = APIRouter(prefix="/compendium")
router.include_router(country_router)
router.include_router(region_router)
router.include_router(poi_router)
router.include_router(card_router)
router.include_router(post_router)
router.include_router(m2m_router)
