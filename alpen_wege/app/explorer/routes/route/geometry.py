# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord as G
from app.explorer.schemas.route import RouteGeometry
from app.explorer.services import route_geometry as rg
from app.explorer.services.route_view import item_dict, route_links, segment_facts

from ._router import router


@router.get("/{route_id}/geometry", response_model=ApiResponse[RouteGeometry])
async def get_route_geometry(
    route_id: UUID,
    access: AccessContext = Depends(resource_access("route", "read")),
    db: AsyncSession = Depends(get_db),
):
    # The map line and the elevation profile of the whole default path (segments in slot order, reversed ones turned
    # around, the distances of each segment added to the ones before), and the alternatives as separate lines.
    route = await db.get(ExplorerAggRoute, route_id)
    check_object_access(access, route, not_found_msg="Route not found")
    links = sorted(await route_links(db, route.id), key=lambda l: (l.slot_position, not l.is_default))
    facts = await segment_facts(db, [l.segment_id for l in links])
    geo_ids = [facts[l.segment_id].segment.geo_record_id for l in links]
    maps = {r.id: r for r in (await db.execute(select(G.id, G.geojson, G.elevation_graph).where(G.id.in_(geo_ids)))).all()} if geo_ids else {}

    def part(link):
        seg = facts[link.segment_id].segment
        m = maps.get(seg.geo_record_id)
        return rg.GeoPart(link.slot_position, seg.id, link.is_reversed, m.geojson if m else None, m.elevation_graph if m else None, facts[link.segment_id].geo.distance_m)

    defaults = [l for l in links if l.is_default]
    alternatives = [
        {"slot_position": l.slot_position, "segment_id": l.segment_id,
         "geojson": rg.line_geojson(rg.route_lines([part(l)]))}
        for l in links if not l.is_default
    ]
    items = [item_dict(l, facts[l.segment_id]) for l in defaults]
    return ok({
        "geojson": rg.line_geojson(rg.route_lines([part(l) for l in defaults])),
        "elevation_graph": rg.combined_profile([part(l) for l in defaults]),
        "alternatives": alternatives,
        "start_point": items[0]["start_point"] if items else None,
        "end_point": items[-1]["end_point"] if items else None,
    })
