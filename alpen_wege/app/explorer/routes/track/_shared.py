# Local application
from app.core.utils.responses import AppError
from app.profile.permissions import AccessContext
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.schemas.track import (
    TrackMetrics,
)


def apply_visibility(stmt, access: AccessContext, archived: bool):
    if archived:
        stmt = stmt.where(ExplorerAggTrack.archived_at.isnot(None))
        if access.scope != "all":
            stmt = stmt.where(ExplorerAggTrack.created_by == access.user.id)
    else:
        stmt = stmt.where(ExplorerAggTrack.archived_at.is_(None))

    if access.scope not in ("own", "all"):
        stmt = stmt.where(
            (ExplorerAggTrack.created_by == access.user.id)
            | (ExplorerAggTrack.processing_status == "ready")
        )

    return stmt


def ensure_visible(access: AccessContext, track: ExplorerAggTrack):
    if access.scope == "all":
        return
    if track.created_by == access.user.id:
        return
    if track.processing_status != "ready" or track.archived_at is not None:
        raise AppError(404, "Not found")


def build_metrics(geo_record, geo_perf) -> TrackMetrics | None:
    if geo_record is None:
        return None
    return TrackMetrics(
        distance_m=geo_record.distance_m,
        elevation_gain_m=geo_record.elevation_gain_m,
        elevation_loss_m=geo_record.elevation_loss_m,
        highest_elevation_m=geo_record.highest_elevation_m,
        lowest_elevation_m=geo_record.lowest_elevation_m,
        total_time_s=geo_perf.total_time_s if geo_perf else None,
        moving_time_s=geo_perf.moving_time_s if geo_perf else None,
    )
