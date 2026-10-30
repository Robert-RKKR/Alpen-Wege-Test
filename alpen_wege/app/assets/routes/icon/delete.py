from uuid import UUID

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.services.icon_usage import icon_usage
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.utils.event_logger import log_deleted
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


def _in_use(counts: dict[str, int]) -> AppError:
    used = ", ".join(f"{n} {what}(s)" for what, n in counts.items() if n)
    text = f"This icon is used by {used} and cannot be deleted. Give them another icon first."
    return AppError(409, "Conflict", error_message=text, error_errors=[{"field": None, "code": "in_use", "message": text}])


@router.delete(
    "/{icon_id}",
    response_model=ApiResponse[None],
    description="Deletes the icon. `409` while a country, region or reference value (sport type, rarity, ...) still uses it.",
)
async def delete_icon(
    icon_id: UUID,
    access: AccessContext = Depends(resource_access("icon", "delete")),
    db: AsyncSession = Depends(get_db),
):
    icon = await db.get(AssetAggIcon, icon_id)
    check_object_access(access, icon, not_found_msg="Icon not found")
    usage = await icon_usage(db, icon_id)
    if any(usage.values()):
        raise _in_use(usage)
    log_deleted(db, icon, access.user.id)
    try:
        await db.delete(icon)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _in_use(await icon_usage(db, icon_id))
    return ok(None, message="Deleted")
