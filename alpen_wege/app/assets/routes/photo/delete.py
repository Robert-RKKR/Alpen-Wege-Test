from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.assets.services.photo_storage import delete_quietly
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.explorer.models.models_agg.segment import ExplorerAggSegment
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.management.utils.event_logger import log_deleted
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router

_USERS = {"card": CompendiumCatCard, "POI": CompendiumCatPoi, "post": CompendiumCatPost,
          "gear": ExplorerAggGear, "segment": ExplorerAggSegment, "track": ExplorerAggTrack}


def _in_use(counts: dict[str, int]) -> AppError:
    used = ", ".join(f"{n} {what}(s)" for what, n in counts.items() if n)
    text = f"This photo is the main photo of {used} and cannot be deleted. Choose another photo for them first."
    return AppError(409, "Conflict", error_message=text, error_errors=[{"field": None, "code": "in_use", "message": text}])


async def _usage(db: AsyncSession, photo_id: UUID) -> dict[str, int]:
    parts = [select(literal(what).label("w"), func.count()).where(m.main_photo_id == photo_id) for what, m in _USERS.items()]
    return {w: n for w, n in (await db.execute(union_all(*parts))).all()}


@router.delete(
    "/{photo_id}",
    response_model=ApiResponse[None],
    description="Deletes the photo and its file. `409` while it is the main photo of a card, POI, post, gear, segment or track.",
)
async def delete_photo(
    photo_id: UUID,
    access: AccessContext = Depends(resource_access("photo", "delete")),
    db: AsyncSession = Depends(get_db),
):
    photo = await db.get(AssetAggPhoto, photo_id)
    check_object_access(access, photo, not_found_msg="Photo not found")
    usage = await _usage(db, photo_id)
    if any(usage.values()):
        raise _in_use(usage)
    path = photo.path
    log_deleted(db, photo, access.user.id)
    try:
        await db.delete(photo)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _in_use(await _usage(db, photo_id))
    await run_in_threadpool(delete_quietly, path)
    return ok(None, message="Deleted")
