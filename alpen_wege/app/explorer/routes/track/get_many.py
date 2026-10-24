# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.models.models_sub.geo_performance import ExplorerSubGeoPerformance
from app.explorer.schemas.track import (
    TrackListItem,
)
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import apply_visibility, build_metrics


@router.get("", response_model=ApiResponse[list[TrackListItem]])
async def list_tracks(
    limit: int = 100,
    offset: int = 0,
    archived: bool = False,
    processing_status: str | None = None,
    sport_type_id: UUID | None = None,
    access: AccessContext = Depends(resource_access("track", "read")),
    db: AsyncSession = Depends(get_db),
):
    if limit > 500:
        limit = 500

    if processing_status and processing_status not in (
        "pending", "processing", "ready", "failed"
    ):
        raise AppError(422, f"Invalid processing_status: {processing_status}")

    base = select(ExplorerAggTrack)
    base = apply_scope(base, ExplorerAggTrack, access)
    base = apply_visibility(base, access, archived)

    if processing_status:
        base = base.where(ExplorerAggTrack.processing_status == processing_status)
    if sport_type_id:
        base = base.where(ExplorerAggTrack.sport_type_id == sport_type_id)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        base.outerjoin(
            ExplorerSubGeoRecord,
            ExplorerSubGeoRecord.id == ExplorerAggTrack.geo_record_id,
        )
        .outerjoin(
            ExplorerSubGeoPerformance,
            ExplorerSubGeoPerformance.id == ExplorerSubGeoRecord.geo_performance_id,
        )
        .add_columns(ExplorerSubGeoRecord, ExplorerSubGeoPerformance)
        .order_by(
            func.coalesce(ExplorerAggTrack.recorded_at, ExplorerAggTrack.created_at).desc()
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()

    items = []
    for track, geo_rec, geo_perf in rows:
        item = TrackListItem(
            id=track.id,
            name=track.name,
            summary=track.summary,
            is_public=track.is_public,
            sport_type_id=track.sport_type_id,
            recorded_at=track.recorded_at,
            created_at=track.created_at,
            processing_status=track.processing_status,
            archived_at=track.archived_at,
            created_by=track.created_by,
            metrics=build_metrics(geo_rec, geo_perf),
        )
        items.append(item)

    return ok_list(items, total=total, limit=limit, offset=offset)
