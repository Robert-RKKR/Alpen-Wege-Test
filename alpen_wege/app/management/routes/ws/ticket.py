# Standard library
import secrets

# Third-party
from fastapi import Depends

# Local application
from app.core.utils.responses import ApiResponse, ok
from app.management.jobs.events import (
    TICKET_PREFIX,
)
from app.management.runtime_settings.service import get_setting
from app.management.schemas.ws import WsTicket
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser
from app.redis import get_redis_pool

from ._router import router


@router.post("/ws/ticket", response_model=ApiResponse[WsTicket])
async def create_ws_ticket(user: ProfileUsrUser = Depends(get_current_active_user)):
    # A bearer token cannot be sent on a browser WebSocket, and tokens here rotate.
    # So: exchange the token for a short-lived, single-use ticket that goes in the URL.
    ttl = await get_setting("ws.ticket_ttl_s")
    ticket = secrets.token_urlsafe(32)
    await get_redis_pool().set(f"{TICKET_PREFIX}{ticket}", str(user.id), ex=ttl)
    return ok(WsTicket(ticket=ticket, expires_in=ttl))
