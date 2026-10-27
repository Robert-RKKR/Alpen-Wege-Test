# Third-party
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.utils.responses import ok
from app.explorer.services.gpx.models import ProcessedGpx
from app.explorer.services.segment_persist import add_segment, ensure_refs
from app.explorer.services.segment_view import geo_info, read_dict
from app.management.utils.event_logger import log_created


async def finish_create(db: AsyncSession, user, processed: ProcessedGpx, fields: dict):
    # The same last steps for every way of making a segment: check the references, write the geo record and the segment,
    # log it, commit, and answer with the new segment (201).
    await ensure_refs(db, fields)
    segment = await add_segment(db, processed, user_id=user.id, fields=fields)
    log_created(db, segment, user.id)
    await db.commit()
    await db.refresh(segment)
    info = await geo_info(db, [segment.geo_record_id])
    data = read_dict(segment, info.get(segment.geo_record_id))
    data["warnings"] = list(processed.warnings)
    return ok(data, code=201, message="Created")
