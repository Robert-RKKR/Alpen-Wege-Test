# Standard library
import logging
from datetime import datetime, timezone

# Third-party
from fastapi import Depends

# Local application
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.jobs.events import publish_notice
from app.management.schemas.broadcast import BroadcastCreate, BroadcastResult
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only

logger = logging.getLogger(__name__)


@router.post("", response_model=ApiResponse[BroadcastResult])
async def send_broadcast(body: BroadcastCreate, admin: ProfileUsrUser = Depends(admin_only)):
    expires_at = body.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise AppError(422, "Validation failed", error_message="expires_at must be in the future.")
    delivered = await publish_notice(body.level, body.text, expires_at)
    logger.info("Broadcast by %s (%s) to %d sockets", admin.id, body.level, delivered)
    return ok(BroadcastResult(delivered_to=delivered), message="Broadcast sent")
