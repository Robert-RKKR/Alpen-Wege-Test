# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, at_least, at_most, contains, equals, ids_query, near_condition, number_query, one_of, page_params,
    search_query, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.core.utils.scope import apply_scope
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.segment import ExplorerAggSegment
from app.explorer.models.models_m2m.segment_route import ExplorerM2mSegmentRoute
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.schemas.segment import SegmentRead
from app.explorer.services.segment_view import computed_of, geo_columns, read_dict

from ._router import router

M = ExplorerAggSegment
G = ExplorerSubGeoRecord
SORT = {
    "name": M.name,
    "created_at": M.created_at,
    "updated_at": M.updated_at,
    "distance_m": G.distance_m,
    "elevation_gain_m": G.elevation_gain_m,
}


class SegmentFilters:
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        sport_type_id: list[UUID] | None = ids_query("Sport type"),
        difficulty_level_id: list[UUID] | None = ids_query("Difficulty level"),
        difficulty_sport_id: list[UUID] | None = ids_query("Sport difficulty"),
        created_by: UUID | None = Query(None, description="Segments of this user (use your own id for 'my segments')."),
        is_public: bool | None = Query(None, description="Only public (true) or only private (false) segments."),
        unused: bool | None = Query(None, description="true: segments that no route uses; false: segments that at least one route uses."),
        start_poi_id: UUID | None = Query(None, description="Segments that start at this POI."),
        end_poi_id: UUID | None = Query(None, description="Segments that end at this POI."),
        distance_min: int | None = number_query("Distance in metres, at least."),
        distance_max: int | None = number_query("Distance in metres, at most."),
        elevation_gain_min: int | None = number_query("Ascent in metres, at least."),
        elevation_gain_max: int | None = number_query("Ascent in metres, at most."),
        near: str | None = Query(None, description="lon,lat: segments that start or end within radius_m of this point (to find one that continues a trail)."),
        radius_m: int | None = Query(None, description="Radius for near in metres. Default 5000, at most 100000."),
    ):
        self.q = q
        self.sport_type_id = sport_type_id
        self.difficulty_level_id = difficulty_level_id
        self.difficulty_sport_id = difficulty_sport_id
        self.created_by = created_by
        self.is_public = is_public
        self.unused = unused
        self.start_poi_id = start_poi_id
        self.end_poi_id = end_poi_id
        self.distance_min = distance_min
        self.distance_max = distance_max
        self.elevation_gain_min = elevation_gain_min
        self.elevation_gain_max = elevation_gain_max
        self.near = near
        self.radius_m = radius_m

    def apply(self, stmt):
        used = exists().where(ExplorerM2mSegmentRoute.segment_id == M.id)
        around = [c for c in (near_condition(G.start_location, self.near, self.radius_m), near_condition(G.end_location, self.near, self.radius_m)) if c is not None]
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl),
            one_of(M.sport_type_id, self.sport_type_id),
            one_of(M.difficulty_level_id, self.difficulty_level_id),
            one_of(M.difficulty_sport_id, self.difficulty_sport_id),
            equals(M.created_by, self.created_by),
            equals(M.is_public, self.is_public),
            None if self.unused is None else (~used if self.unused else used),
            equals(M.start_poi_id, self.start_poi_id),
            equals(M.end_poi_id, self.end_poi_id),
            at_least(G.distance_m, self.distance_min),
            at_most(G.distance_m, self.distance_max),
            at_least(G.elevation_gain_m, self.elevation_gain_min),
            at_most(G.elevation_gain_m, self.elevation_gain_max),
            or_(*around) if around else None,
        )


@router.get("", response_model=ApiResponse[list[SegmentRead]])
async def list_segments(
    access: AccessContext = Depends(resource_access("segment", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "-created_at", M.id)),
    filters: SegmentFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = apply_scope(select(M).join(G, G.id == M.geo_record_id), M, access)
    base = filters.apply(base)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = sort.apply(base).add_columns(*geo_columns()).limit(page.limit).offset(page.offset)
    rows = (await db.execute(stmt)).all()
    items = []
    for row in rows:
        segment = row[0]
        items.append({**read_dict(segment, None), **computed_of(row)})
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
