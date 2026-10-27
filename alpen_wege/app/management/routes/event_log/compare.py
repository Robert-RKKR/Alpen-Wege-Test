# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.models.event_log import MgmtLogEvent
from app.management.schemas.event_log import (
    EventLogCompare,
    EventLogDetail,
)
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("/{id_1}/compare/{id_2}", response_model=ApiResponse[EventLogCompare])
async def compare_event_logs(
    id_1: UUID,
    id_2: UUID,
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    plan: ExpandPlan = Depends(expand_plan(EventLogDetail)),
    db: AsyncSession = Depends(get_db),
):
    if id_1 == id_2:
        raise AppError(400, "Bad request", error_message="Choose two different entries.")

    res = await db.execute(
        select(MgmtLogEvent)
        .options(*plan.load_options(MgmtLogEvent))
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

    older_d, newer_d = plan.render(older, viewer=_user), plan.render(newer, viewer=_user)

    def ref(d):
        return {
            "id": d["id"], "seq": d["seq"], "action": d["action"],
            "changed_by": d["changed_by"], "changed_at": d["changed_at"],
            "request_id": d["request_id"], "changed_by_user": d["changed_by_user"],
        }

    return ok({
        "entity_type": older_d["entity_type"],
        "entity_id": older.entity_id,
        "older": ref(older_d),
        "newer": ref(newer_d),
        "events_between": len(rows) - 1,
        "changes": changes,
        "warnings": warnings,
    })
