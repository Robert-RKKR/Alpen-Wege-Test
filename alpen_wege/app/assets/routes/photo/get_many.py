from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.assets.schemas.asset import PhotoRead
from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, at_least, at_most, bbox_condition, before, contains, equals, moment_query, near_condition, number_query,
    page_params, search_query, since, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.core.utils.scope import apply_scope
from app.profile.permissions import AccessContext, resource_access

from ._router import router

M = AssetAggPhoto
SORT = {"name": M.name, "taken_at": M.taken_at, "altitude_m": M.altitude_m, "created_at": M.created_at}


class PhotoFilters:
    def __init__(
        self,
        q: str | None = search_query("name or summary in English, German or Polish"),
        created_by: UUID | None = Query(None, description="Photos of this user."),
        is_public: bool | None = Query(None, description="Only public (true) or only private (false) photos."),
        altitude_min: int | None = number_query("Altitude in metres, at least."),
        altitude_max: int | None = number_query("Altitude in metres, at most."),
        taken_from: moment_query("Taken at or after this date or time.") = None,
        taken_to: moment_query("Taken before this date or time.") = None,
        created_from: moment_query("Created at or after this date or time.") = None,
        created_to: moment_query("Created before this date or time.") = None,
        bbox: str | None = Query(None, description="Inside a box: min_lon,min_lat,max_lon,max_lat (west, south, east, north)."),
        near: str | None = Query(None, description="Around a point: lon,lat. Use radius_m for the distance."),
        radius_m: int | None = Query(None, description="Distance around near in metres. Default 5000, at most 100000."),
    ):
        self.q = q
        self.created_by = created_by
        self.is_public = is_public
        self.altitude_min = altitude_min
        self.altitude_max = altitude_max
        self.taken_from = taken_from
        self.taken_to = taken_to
        self.created_from = created_from
        self.created_to = created_to
        self.bbox = bbox
        self.near = near
        self.radius_m = radius_m

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl, M.summary, M.summary_de, M.summary_pl),
            equals(M.created_by, self.created_by),
            equals(M.is_public, self.is_public),
            at_least(M.altitude_m, self.altitude_min),
            at_most(M.altitude_m, self.altitude_max),
            since(M.taken_at, self.taken_from),
            before(M.taken_at, self.taken_to),
            since(M.created_at, self.created_from),
            before(M.created_at, self.created_to),
            bbox_condition(M.location, self.bbox),
            near_condition(M.location, self.near, self.radius_m),
        )


@router.get("", response_model=ApiResponse[list[PhotoRead]])
async def list_photos(
    access: AccessContext = Depends(resource_access("photo", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "-created_at", M.id)),
    filters: PhotoFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = sort.apply(base).limit(page.limit).offset(page.offset)
    items = (await db.execute(stmt)).scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
