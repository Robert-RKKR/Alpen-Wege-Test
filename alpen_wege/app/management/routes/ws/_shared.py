# Standard library
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

# Third-party
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select
from starlette.websockets import WebSocketState

# Local application
from app.database import AsyncSessionLocal
from app.management.jobs.events import (
    CONN_PREFIX, TICKET_PREFIX,
)
from app.management.models.job import MgmtLogJob
from app.management.runtime_settings.service import get_setting
from app.management.schemas.job import JobRead
from app.redis import get_redis_pool

logger = logging.getLogger(__name__)


CLOSE_UNAUTHORIZED = 4401   # bad ticket, or logout
CLOSE_FORBIDDEN = 4403      # account deactivated
CLOSE_NOT_FOUND = 4404      # dedicated socket: not your job, or no such job
CLOSE_RECONNECT = 4408      # maximum lifetime reached: get a new ticket and reconnect
CLOSE_TOO_MANY = 4429       # too many open sockets for this user
MAX_CLIENT_MESSAGE_CHARS = 1024
TERMINAL = ("succeeded", "failed", "cancelled")


async def consume_ticket(ticket: str) -> uuid.UUID | None:
    raw = await get_redis_pool().getdel(f"{TICKET_PREFIX}{ticket}")  # works once
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


async def register_connection(user_id, conn_id: str, max_conns: int, lifetime: int) -> bool:
    # Sorted set of open sockets; the score is an expiry time, so a crashed process cannot
    # leave a permanent count behind.
    redis = get_redis_pool()
    key = f"{CONN_PREFIX}{user_id}"
    now = time.time()
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", now)
    pipe.zadd(key, {conn_id: now + lifetime + 30})
    pipe.zcard(key)
    pipe.expire(key, lifetime + 60)
    _, _, count, _ = await pipe.execute()
    if count > max_conns:
        await redis.zrem(key, conn_id)
        return False
    return True


def dump(job) -> dict:
    return JobRead.model_validate(job).model_dump(mode="json")


async def general_snapshot(user_id: uuid.UUID) -> dict:
    minutes = await get_setting("jobs.recent_finished_minutes")
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(MgmtLogJob)
            .where(
                MgmtLogJob.user_id == user_id,
                or_(MgmtLogJob.status.in_(("queued", "running")), MgmtLogJob.finished_at > since),
            )
            .order_by(MgmtLogJob.created_at.desc())
            .limit(200)
        )).scalars().all()
    return {"type": "sync", "jobs": [dump(r) for r in rows], "server_time": now.isoformat()}


async def job_snapshot(user_id: uuid.UUID, job_id: uuid.UUID) -> dict | None:
    async with AsyncSessionLocal() as session:
        job = (await session.execute(
            select(MgmtLogJob).where(MgmtLogJob.id == job_id, MgmtLogJob.user_id == user_id)
        )).scalar_one_or_none()
    if job is None:
        return None
    return {"type": "sync", "jobs": [dump(job)], "server_time": datetime.now(timezone.utc).isoformat()}


def close_code_for(reason: str | None) -> int:
    return CLOSE_FORBIDDEN if reason == "deactivated" else CLOSE_UNAUTHORIZED


def parse(data: str) -> dict:
    try:
        parsed = json.loads(data)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


async def serve(websocket: WebSocket, user_id: uuid.UUID, channels: list[str], snapshot, *, close_on_terminal: bool) -> None:
    redis = get_redis_pool()
    max_conns = await get_setting("ws.max_connections_per_user")
    lifetime = await get_setting("ws.max_lifetime_s")
    conn_id = uuid.uuid4().hex

    if not await register_connection(user_id, conn_id, max_conns, lifetime):
        await websocket.close(code=CLOSE_TOO_MANY)
        return

    pubsub = redis.pubsub()
    try:
        # Subscribe first, then read the snapshot, so no event can fall into a gap.
        await pubsub.subscribe(*channels)
        first = await snapshot()
        await websocket.send_text(json.dumps(first))
        jobs = first.get("jobs", [])
        if close_on_terminal and jobs and jobs[0]["status"] in TERMINAL:
            await websocket.close(code=1000)
            return

        async def forward():
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message["data"]
                await websocket.send_text(data)
                event = parse(data)
                if event.get("type") == "control" and event.get("action") == "close":
                    await websocket.close(code=close_code_for(event.get("reason")))
                    return
                if (
                    close_on_terminal and event.get("type") == "job.update"
                    and event.get("job", {}).get("status") in TERMINAL
                ):
                    await websocket.close(code=1000)
                    return

        async def receive():
            # The client sends nothing we need; reading detects a closed connection.
            try:
                while True:
                    text = await websocket.receive_text()
                    if len(text) > MAX_CLIENT_MESSAGE_CHARS:
                        await websocket.close(code=1009)
                        return
            except Exception:
                return

        async def lifetime_timer():
            await asyncio.sleep(lifetime)
            await websocket.close(code=CLOSE_RECONNECT)

        tasks = [asyncio.create_task(c()) for c in (forward, receive, lifetime_timer)]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, (WebSocketDisconnect, RuntimeError)):
                logger.warning("WebSocket task failed", exc_info=exc)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe(*channels)
            try:
                await pubsub.aclose()
            except AttributeError:
                await pubsub.close()
        except Exception:
            pass
        try:
            await redis.zrem(f"{CONN_PREFIX}{user_id}", conn_id)
        except Exception:
            pass
        if websocket.application_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
