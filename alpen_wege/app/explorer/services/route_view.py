# Standard library
from dataclasses import dataclass
from uuid import UUID

# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.models.models_ref import CoreRefDifficultyLevel as DL, CoreRefDifficultySport as DS
from app.explorer.models.models_agg.segment import ExplorerAggSegment as S
from app.explorer.models.models_m2m.segment_route import ExplorerM2mSegmentRoute as Link
from app.explorer.models.models_sub.plan_conditions import ExplorerSubPlanConditions
from app.explorer.services import aggregate
from app.explorer.services.continuity import EndPoint, SlotItem
from app.explorer.services.segment_view import geo_columns, point_of


@dataclass
class RowSpec:
    # the four fields of a segment row that the checks read, for rows that are not saved (the validate endpoint)
    slot_position: int
    alt_group: int | None
    is_default: bool
    is_reversed: bool


@dataclass
class Facts:
    # a segment together with what the checks and the totals need from its geo record and from the ranks
    segment: S
    geo: object                 # row of segment_view.geo_columns()
    level_rank: int | None
    grade_rank: int | None
    grade_sport_type_id: UUID | None


async def segment_facts(db: AsyncSession, segment_ids, lock: bool = False) -> dict[UUID, Facts]:
    # lock=True takes a shared row lock on the segments until the end of the transaction: a save that adds a segment to a
    # route and the owner who makes it private at the same moment cannot both pass their checks
    ids = list({i for i in segment_ids if i is not None})
    if not ids:
        return {}
    from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord as G
    stmt = (
        select(S, DL.rank.label("level_rank"), DS.rank.label("grade_rank"), DS.sport_type_id.label("grade_sport_type_id"), *geo_columns())
        .join(G, G.id == S.geo_record_id)
        .outerjoin(DL, DL.id == S.difficulty_level_id)
        .outerjoin(DS, DS.id == S.difficulty_sport_id)
        .where(S.id.in_(ids))
    )
    if lock:
        stmt = stmt.with_for_update(read=True, of=S)
    out = {}
    for row in (await db.execute(stmt)).all():
        out[row[0].id] = Facts(row[0], row, row.level_rank, row.grade_rank, row.grade_sport_type_id)
    return out


async def route_links(db: AsyncSession, route_id) -> list[Link]:
    stmt = (
        select(Link).where(Link.route_id == route_id)
        .order_by(Link.slot_position, Link.is_default.desc(), Link.created_at, Link.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def _end(lon, lat, poi_id) -> EndPoint | None:
    return None if lon is None or lat is None else EndPoint(lon, lat, poi_id)


def slot_item(link, facts: Facts) -> SlotItem:
    seg, geo = facts.segment, facts.geo
    return SlotItem(
        ref=str(seg.id), slot=link.slot_position, is_default=link.is_default, is_reversed=link.is_reversed,
        start=_end(geo.start_lon, geo.start_lat, seg.start_poi_id), end=_end(geo.end_lon, geo.end_lat, seg.end_poi_id),
        alt_group=link.alt_group, segment_id=seg.id,
    )


def default_seg(link, facts: Facts) -> aggregate.DefaultSeg:
    seg, geo = facts.segment, facts.geo
    return aggregate.DefaultSeg(
        slot=link.slot_position, segment_id=seg.id, is_reversed=link.is_reversed, sport_type_id=seg.sport_type_id,
        difficulty_level_id=seg.difficulty_level_id, difficulty_level_rank=facts.level_rank,
        difficulty_sport_id=seg.difficulty_sport_id, difficulty_sport_rank=facts.grade_rank,
        difficulty_sport_sport_type_id=facts.grade_sport_type_id,
        distance_m=geo.distance_m, elevation_gain_m=geo.elevation_gain_m, elevation_loss_m=geo.elevation_loss_m,
        highest_elevation_m=geo.highest_elevation_m, lowest_elevation_m=geo.lowest_elevation_m,
    )


def item_dict(link, facts: Facts) -> dict:
    # one row of the route's segment list, as the route walks it: start and end swapped and ascent and descent exchanged
    # for a reversed segment
    seg, geo = facts.segment, facts.geo
    rev = link.is_reversed
    gain, loss = (geo.elevation_loss_m, geo.elevation_gain_m) if rev else (geo.elevation_gain_m, geo.elevation_loss_m)
    start, end = (point_of(geo.end_lon, geo.end_lat), point_of(geo.start_lon, geo.start_lat)) if rev else (
        point_of(geo.start_lon, geo.start_lat), point_of(geo.end_lon, geo.end_lat))
    start_poi, end_poi = (seg.end_poi_id, seg.start_poi_id) if rev else (seg.start_poi_id, seg.end_poi_id)
    return {
        "segment_id": seg.id, "slot_position": link.slot_position, "alt_group": link.alt_group, "is_default": link.is_default,
        "is_reversed": rev, "name": seg.name, "sport_type_id": seg.sport_type_id,
        "difficulty_level_id": seg.difficulty_level_id, "difficulty_sport_id": seg.difficulty_sport_id,
        "distance_m": geo.distance_m, "elevation_gain_m": gain, "elevation_loss_m": loss,
        "highest_elevation_m": geo.highest_elevation_m, "lowest_elevation_m": geo.lowest_elevation_m,
        "start_point": start, "end_point": end, "start_poi_id": start_poi, "end_poi_id": end_poi,
        "is_public": seg.is_public, "created_by": seg.created_by,
    }


def apply_state(route, links: list, facts: dict[UUID, Facts]) -> dict:
    # The totals of the default segments and the classification (only fields that are empty). Sets them on the route and
    # returns the derived values.
    defaults = [default_seg(l, facts[l.segment_id]) for l in links if l.is_default]
    for name, value in aggregate.route_totals(defaults).items():
        setattr(route, name, value)
    derived = aggregate.derive_classification(defaults)
    aggregate.fill_empty_classification(route, derived)
    return derived


async def plan_conditions_of(db: AsyncSession, route) -> ExplorerSubPlanConditions | None:
    return None if route.plan_condition_id is None else await db.get(ExplorerSubPlanConditions, route.plan_condition_id)


async def route_extras(db: AsyncSession, route, links: list | None = None, facts: dict | None = None) -> dict:
    # The fields of RouteDetail that are not columns of the route: the segment list, the sports of the default segments,
    # the classification as it would be computed now, whether it differs from the stored one, and the plan conditions.
    links = await route_links(db, route.id) if links is None else links
    facts = await segment_facts(db, [l.segment_id for l in links]) if facts is None else facts
    ordered = sorted(links, key=lambda l: (l.slot_position, not l.is_default))
    defaults = [default_seg(l, facts[l.segment_id]) for l in ordered if l.is_default]
    derived = aggregate.derive_classification(defaults)
    conditions = await plan_conditions_of(db, route)
    return {
        "segments": [item_dict(l, facts[l.segment_id]) for l in ordered],
        "sport_types": aggregate.sport_breakdown(defaults),
        "derived": derived,
        "classification_differs": aggregate.classification_differs(route, derived) if defaults else False,
        "plan_conditions": None if conditions is None else {c.key: getattr(conditions, c.key) for c in ExplorerSubPlanConditions.__table__.columns if c.key not in ("created_at", "updated_at")},
    }
