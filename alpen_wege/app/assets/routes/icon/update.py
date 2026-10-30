from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.schemas.asset import IconRead, IconUpdate
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.utils.event_logger import log_updated
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router
from ._shared import key_taken


@router.patch(
    "/{icon_id}",
    response_model=ApiResponse[IconRead],
    description="Changes the names, summaries or key of an icon. The SVG is replaced with `PUT /assets/icons/{id}/file`. Links are by id, so a new key breaks nothing (`409` when the key exists).",
)
async def update_icon(
    icon_id: UUID,
    body: IconUpdate,
    access: AccessContext = Depends(resource_access("icon", "update")),
    db: AsyncSession = Depends(get_db),
):
    icon = await db.get(AssetAggIcon, icon_id)
    check_object_access(access, icon, not_found_msg="Icon not found")
    changes = body.model_dump(exclude_unset=True)
    for required in ("name", "key"):
        if changes.get(required, "") is None:
            changes.pop(required)          # null on a required field means: leave it
    if "key" in changes and changes["key"] != icon.key:
        if (await db.execute(select(AssetAggIcon.id).where(AssetAggIcon.key == changes["key"]))).first():
            raise key_taken()
    old_values = {f: getattr(icon, f) for f in changes}
    for field, value in changes.items():
        setattr(icon, field, value)
    log_updated(db, icon, old_values, changes, access.user.id)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise key_taken()
    await db.refresh(icon)
    return ok(icon)
