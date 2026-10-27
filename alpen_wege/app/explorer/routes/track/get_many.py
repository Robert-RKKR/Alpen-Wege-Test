# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import (
    PAGE_100_MAX_500, Page, Sort, at_least, at_most, before, contains, equals, ids_query, number_query, one_of, page_params,
    search_query, since, sort_params, where_all, moment_query,
)
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

M = ExplorerAggTrack
G = ExplorerSubGeoRecord
SORT = {
    "recorded_at": func.coalesce(M.recorded_at, M.created_at),   # the recording time, the upload time when there is none
    "created_at": M.created_at,
    "name": M.name,
    "distance_m": G.distance_m,
    "elevation_gain_m": G.elevation_gain_m,
}


class TrackFilters:
    def __init__(
        self,
        archived: bool = Query(False, description="true: the archived tracks (the owner's, or all for an administrator)."),
        processing_status: str | None = Query(None, description="pending, processing, ready or failed."),
        sport_type_id: list[UUID] | None = ids_query("Sport type"),
        q: str | None = search_query("name or summary in English, German or Polish"),
        is_public: bool | None = Query(None, description="Only public (true) or only private (false) tracks."),
        created_by: UUID | None = Query(None, description="Tracks of this user."),
        difficulty_level_id: list[UUID] | None = ids_query("Difficulty level"),
        difficulty_sport_id: list[UUID] | None = ids_query("Sport difficulty"),
        start_poi_id: UUID | None = Query(None, description="Tracks that start at this POI."),
        end_poi_id: UUID | None = Query(None, description="Tracks that end at this POI."),
        recorded_from: moment_query("Recorded at or after this date or time.") = None,
        recorded_to: moment_query("Recorded before this date or time.") = None,
        distance_min: int | None = number_query("Distance in metres, at least."),
        distance_max: int | None = number_query("Distance in metres, at most."),
        elevation_gain_min: int | None = number_query("Ascent in metres, at least."),
        elevation_gain_max: int | None = number_query("Ascent in metres, at most."),
    ):
        if processing_status and processing_status not in (
            "pending", "processing", "ready", "failed"
        ):
            raise AppError(422, f"Invalid processing_status: {processing_status}")
        self.archived = archived
        self.processing_status = processing_status
        self.sport_type_id = sport_type_id
        self.q = q
        self.is_public = is_public
        self.created_by = created_by
        self.difficulty_level_id = difficulty_level_id
        self.difficulty_sport_id = difficulty_sport_id
        self.start_poi_id = start_poi_id
        self.end_poi_id = end_poi_id
        self.recorded_from = recorded_from
        self.recorded_to = recorded_to
        self.distance_min = distance_min
        self.distance_max = distance_max
        self.elevation_gain_min = elevation_gain_min
        self.elevation_gain_max = elevation_gain_max

    def apply(self, stmt):
        recorded = func.coalesce(M.recorded_at, M.created_at)
        return where_all(
            stmt,
            equals(M.processing_status, self.processing_status),
            one_of(M.sport_type_id, self.sport_type_id),
            contains(self.q, M.name, M.name_de, M.name_pl, M.summary),
            equals(M.is_public, self.is_public),
            equals(M.created_by, self.created_by),
            one_of(M.difficulty_level_id, self.difficulty_level_id),
            one_of(M.difficulty_sport_id, self.difficulty_sport_id),
            equals(M.start_poi_id, self.start_poi_id),
            equals(M.end_poi_id, self.end_poi_id),
            since(recorded, self.recorded_from),
            before(recorded, self.recorded_to),
            at_least(G.distance_m, self.distance_min),
            at_most(G.distance_m, self.distance_max),
            at_least(G.elevation_gain_m, self.elevation_gain_min),
            at_most(G.elevation_gain_m, self.elevation_gain_max),
        )


@router.get("", response_model=ApiResponse[list[TrackListItem]])
async def list_tracks(
    access: AccessContext = Depends(resource_access("track", "read")),
    page: Page = Depends(page_params(PAGE_100_MAX_500)),
    sort: Sort = Depends(sort_params(SORT, "-recorded_at", M.id)),
    filters: TrackFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = select(M).outerjoin(G, G.id == M.geo_record_id)
    base = apply_scope(base, M, access)
    base = apply_visibility(base, access, filters.archived)
    base = filters.apply(base)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = (
        sort.apply(
            base.outerjoin(
                ExplorerSubGeoPerformance,
                ExplorerSubGeoPerformance.id == G.geo_performance_id,
            )
            .add_columns(G, ExplorerSubGeoPerformance)
        )
        .limit(page.limit)
        .offset(page.offset)
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
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
