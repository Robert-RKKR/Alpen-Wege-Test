from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.assets.models.models_agg.gpx import AssetAggGpx
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.services.gpx_storage import delete_quietly
from app.management.utils.event_logger import log_deleted
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


def _in_use(n: int) -> AppError:
    text = f"This GPX file belongs to {n} track(s) and cannot be deleted. Delete the track instead."
    return AppError(409, "Conflict", error_message=text, error_errors=[{"field": None, "code": "in_use", "message": text}])


async def _usage(db: AsyncSession, gpx_id: UUID) -> int:
    tracks = select(func.count()).where(ExplorerAggTrack.gpx_id == gpx_id).scalar_subquery()
    records = select(func.count()).where(ExplorerSubGeoRecord.gpx_id == gpx_id).scalar_subquery()
    return (await db.execute(select(tracks + records))).scalar_one()


@router.delete(
    "/{gpx_id}",
    response_model=ApiResponse[None],
    description="Deletes a GPX file that no track uses any more (an orphan). `409` while a track or its geometry uses it.",
)
async def delete_gpx(
    gpx_id: UUID,
    access: AccessContext = Depends(resource_access("gpx", "delete")),
    db: AsyncSession = Depends(get_db),
):
    gpx = await db.get(AssetAggGpx, gpx_id)
    check_object_access(access, gpx, not_found_msg="GPX file not found")
    n = await _usage(db, gpx_id)
    if n:
        raise _in_use(n)
    path = gpx.path
    log_deleted(db, gpx, access.user.id)
    try:
        await db.delete(gpx)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _in_use(await _usage(db, gpx_id))
    await run_in_threadpool(delete_quietly, path)
    return ok(None, message="Deleted")
