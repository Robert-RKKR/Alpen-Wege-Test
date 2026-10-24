# Third-party
from fastapi import Query, WebSocket

# Local application
from app.management.jobs.events import (
    CH_ALL, ch_ctl, ch_user,
)

from ._router import router
from ._shared import CLOSE_UNAUTHORIZED, consume_ticket, general_snapshot, serve


@router.websocket("/ws")
async def ws_general(websocket: WebSocket, ticket: str = Query(...)):
    # General socket: broadcast notices, all my job events, control messages.
    await websocket.accept()
    user_id = await consume_ticket(ticket)
    if user_id is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    await serve(
        websocket, user_id, [CH_ALL, ch_user(user_id), ch_ctl(user_id)],
        lambda: general_snapshot(user_id), close_on_terminal=False,
    )
