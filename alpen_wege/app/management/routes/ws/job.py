# Standard library
import uuid

# Third-party
from fastapi import Query, WebSocket

# Local application
from app.management.jobs.events import (
    ch_ctl, ch_job,
)

from ._router import router
from ._shared import CLOSE_UNAUTHORIZED, CLOSE_NOT_FOUND, consume_ticket, job_snapshot, serve


@router.websocket("/ws/jobs/{job_id}")
async def ws_job(websocket: WebSocket, job_id: uuid.UUID, ticket: str = Query(...)):
    # Dedicated socket: one job, closes when the job ends. Same answer for "not found" and "not yours".
    await websocket.accept()
    user_id = await consume_ticket(ticket)
    if user_id is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    if await job_snapshot(user_id, job_id) is None:
        await websocket.close(code=CLOSE_NOT_FOUND)
        return

    async def snapshot():
        return await job_snapshot(user_id, job_id) or {"type": "sync", "jobs": []}

    await serve(websocket, user_id, [ch_job(job_id), ch_ctl(user_id)], snapshot, close_on_terminal=True)
