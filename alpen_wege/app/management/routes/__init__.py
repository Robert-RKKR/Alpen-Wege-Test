# Third-party
from fastapi import APIRouter

# Local application
from .broadcast import router as broadcast_router
from .celery import router as celery_router
from .event_log import router as event_log_router
from .jobs import router as jobs_router
from .my_jobs import router as my_jobs_router
from .settings import router as settings_router
from .ws import router as ws_router

# User routes (my-jobs, WebSocket) and administrator routes share the /management prefix.
router = APIRouter(prefix="/management")
router.include_router(my_jobs_router)
router.include_router(ws_router)
router.include_router(event_log_router)
router.include_router(settings_router)
router.include_router(jobs_router)
router.include_router(broadcast_router)
router.include_router(celery_router)
