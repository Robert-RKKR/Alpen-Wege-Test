# Standard library
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

# Local application
from app.core.dependencies import get_db
from app.management.models.entity_type import MgmtRefEntityType
from app.management.models.event_log import MgmtLogEvent
from app.management.schemas.event_log import (
    EntityTypeRead,
    EventLogCompare,
    EventLogRead,
)
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser

router = APIRouter(prefix="/event-log", tags=["Management - Event Log"])


@router.get("", response_model=ApiResponse[list[EventLogRead]])
async def list_event_logs(
    limit: int = 100,
    offset: int = 0,
    entity_type: str | None = Query(None, description="Filter by entity type key (table name)"),
    entity_id: UUID | None = Query(None),
    action: str | None = Query(None),
    changed_by: UUID | None = Query(None),
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if entity_type is not None:
        sub = select(MgmtRefEntityType.id).where(MgmtRefEntityType.key == entity_type)
        filters.append(MgmtLogEvent.entity_type_id.in_(sub))
    if entity_id is not None:
        filters.append(MgmtLogEvent.entity_id == entity_id)
    if action is not None:
        filters.append(MgmtLogEvent.action == action)
    if changed_by is not None:
        filters.append(MgmtLogEvent.changed_by == changed_by)

    count_stmt = select(func.count()).select_from(MgmtLogEvent)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(MgmtLogEvent)
        .options(joinedload(MgmtLogEvent.entity_type))
        .order_by(MgmtLogEvent.changed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    for f in filters:
        stmt = stmt.where(f)
    result = await db.execute(stmt)
    items = result.scalars().unique().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.get("/entity-types", response_model=ApiResponse[list[EntityTypeRead]])
async def list_entity_types(
    module: str | None = Query(None, description="Filter by module (e.g. explorer, profile)"),
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MgmtRefEntityType).order_by(MgmtRefEntityType.module, MgmtRefEntityType.key)
    if module is not None:
        stmt = stmt.where(MgmtRefEntityType.module == module)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok(items)


@router.get("/{log_id}", response_model=ApiResponse[EventLogRead])
async def get_event_log(
    log_id: UUID,
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MgmtLogEvent)
        .options(joinedload(MgmtLogEvent.entity_type))
        .where(MgmtLogEvent.id == log_id)
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        raise AppError(404, "Not found", error_message="Event log entry not found.")
    return ok(entry)


@router.get("/{id_1}/compare/{id_2}", response_model=ApiResponse[EventLogCompare])
async def compare_event_logs(
    id_1: UUID,
    id_2: UUID,
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    if id_1 == id_2:
        raise AppError(400, "Bad request", error_message="Choose two different entries.")

    res = await db.execute(
        select(MgmtLogEvent)
        .options(joinedload(MgmtLogEvent.entity_type))
        .where(MgmtLogEvent.id.in_([id_1, id_2]))
    )
    found = {e.id: e for e in res.scalars().unique().all()}
    if id_1 not in found or id_2 not in found:
        raise AppError(404, "Not found", error_message="Event log entry not found.")

    a, b = found[id_1], found[id_2]
    if a.entity_type_id != b.entity_type_id or a.entity_id != b.entity_id:
        raise AppError(
            400, "Bad request",
            error_message="Entries belong to different objects and cannot be compared.",
        )

    older, newer = (a, b) if a.seq < b.seq else (b, a)

    rows = (await db.execute(
        select(MgmtLogEvent)
        .where(
            MgmtLogEvent.entity_type_id == older.entity_type_id,
            MgmtLogEvent.entity_id == older.entity_id,
            MgmtLogEvent.seq > older.seq,
            MgmtLogEvent.seq <= newer.seq,
        )
        .order_by(MgmtLogEvent.seq)
    )).scalars().all()

    net: dict[str, dict] = {}
    warnings: list[str] = []
    for row in rows:
        if row.action != "updated":
            warnings.append(
                f"Range contains a '{row.action}' event (seq {row.seq}); "
                "net changes may be incomplete."
            )
            continue
        for field, delta in row.snapshot.items():
            if field not in net:
                net[field] = {"from": delta["old"], "to": delta["new"]}
            else:
                net[field]["to"] = delta["new"]

    changes = {f: c for f, c in net.items() if c["from"] != c["to"]}

    def ref(e):
        return {
            "id": e.id, "seq": e.seq, "action": e.action,
            "changed_by": e.changed_by, "changed_at": e.changed_at,
            "request_id": e.request_id,
        }

    et = older.entity_type
    return ok({
        "entity_type": {
            "id": et.id, "key": et.key, "display_name": et.display_name,
            "module": et.module, "tracking_mode": et.tracking_mode,
            "ignore_fields": et.ignore_fields,
        },
        "entity_id": older.entity_id,
        "older": ref(older),
        "newer": ref(newer),
        "events_between": len(rows) - 1,
        "changes": changes,
        "warnings": warnings,
    })
