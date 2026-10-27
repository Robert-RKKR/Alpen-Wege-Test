# Third-party
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.assets.models.models_agg.gpx import AssetAggGpx
from app.core.utils.responses import AppError
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.services.gpx_storage import resolve_path
from app.explorer.services.visibility import scope_of


async def clip_source_path(db: AsyncSession, user, track_id):
    # The stored GPX file of a track that the caller may cut a segment from: his own track (or any, with the scope "all"
    # on tracks), processed and not archived. Anything else answers 404 so another user's track is not revealed.
    track = await db.get(ExplorerAggTrack, track_id)
    scope = await scope_of(db, user, "track", "read")
    allowed = track is not None and scope is not None and (scope == "all" or track.created_by == user.id)
    if not allowed or track.archived_at is not None:
        raise AppError(404, "Not found", error_message="The track does not exist or you may not use it.")
    if track.processing_status != "ready" or track.gpx_id is None:
        raise AppError(409, "Conflict", error_message="The track is not processed yet; try again when it is ready.")
    gpx = await db.get(AssetAggGpx, track.gpx_id)
    if gpx is None:
        raise AppError(409, "Conflict", error_message="The GPX file of the track is missing.")
    return resolve_path(gpx.path)
