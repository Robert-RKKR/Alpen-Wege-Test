# Standard library
import logging
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.models.models_sub.geo_performance import ExplorerSubGeoPerformance
from app.explorer.schemas.track import (
    TrackRead,
    TrackUpdate,
)
from app.explorer.services.dispatch import (
    request_stats_recompute,
)

from ._router import router
from ._shared import ensure_visible, build_metrics

logger = logging.getLogger(__name__)


@router.patch("/{track_id}", response_model=ApiResponse[TrackRead])
async def update_track(
    track_id: UUID,
    body: TrackUpdate,
    access: AccessContext = Depends(resource_access("track", "update")),
    db: AsyncSession = Depends(get_db),
):
    track = await db.get(ExplorerAggTrack, track_id)
    check_object_access(access, track, not_found_msg="Track not found")
    ensure_visible(access, track)

    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(track, f) for f in changes}

    for field, value in changes.items():
        setattr(track, field, value)

    log_updated(db, track, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(track)

    sport_changed = (
        "sport_type_id" in changes
        and old_values.get("sport_type_id") != track.sport_type_id
    )
    if sport_changed:
        try:
            await run_in_threadpool(request_stats_recompute, track.created_by)
        except Exception:
            logger.warning("Failed to request stats recompute after sport change")

    geo_rec = None
    geo_perf = None
    if track.geo_record_id:
        geo_rec = await db.get(ExplorerSubGeoRecord, track.geo_record_id)
        if geo_rec and geo_rec.geo_performance_id:
            geo_perf = await db.get(
                ExplorerSubGeoPerformance, geo_rec.geo_performance_id
            )

    result = TrackRead(
        id=track.id,
        name=track.name,
        name_de=track.name_de,
        name_pl=track.name_pl,
        summary=track.summary,
        summary_de=track.summary_de,
        summary_pl=track.summary_pl,
        description=track.description,
        description_de=track.description_de,
        description_pl=track.description_pl,
        is_public=track.is_public,
        processing_status=track.processing_status,
        processing_error=track.processing_error,
        processing_warnings=track.processing_warnings,
        processed_at=track.processed_at,
        recorded_at=track.recorded_at,
        archived_at=track.archived_at,
        sport_type_id=track.sport_type_id,
        difficulty_level_id=track.difficulty_level_id,
        difficulty_sport_id=track.difficulty_sport_id,
        start_poi_id=track.start_poi_id,
        end_poi_id=track.end_poi_id,
        geo_record_id=track.geo_record_id,
        gpx_id=track.gpx_id,
        created_at=track.created_at,
        updated_at=track.updated_at,
        created_by=track.created_by,
        metrics=build_metrics(geo_rec, geo_perf),
    )
    return ok(result)
