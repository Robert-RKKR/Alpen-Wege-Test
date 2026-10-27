# Third-party
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord as G
from app.explorer.schemas.segment import SegmentRead

COMPUTED = {"metrics", "start_point", "end_point"}
METRIC_FIELDS = (
    "distance_m", "elevation_gain_m", "elevation_loss_m", "highest_elevation_m", "lowest_elevation_m",
    "avg_grade", "highest_grade", "total_points",
)


def geo_columns() -> list:
    # the columns of the geo record that a segment shows (no geometry), and its start and end as numbers
    return [
        G.id.label("geo_id"),
        *[getattr(G, name) for name in METRIC_FIELDS],
        func.ST_X(G.start_location).label("start_lon"), func.ST_Y(G.start_location).label("start_lat"),
        func.ST_X(G.end_location).label("end_lon"), func.ST_Y(G.end_location).label("end_lat"),
    ]


async def geo_info(db: AsyncSession, geo_record_ids) -> dict:
    # geo_record_id -> row with the metrics and the start and end point (one query for any number of segments)
    ids = list({i for i in geo_record_ids if i is not None})
    if not ids:
        return {}
    rows = (await db.execute(select(*geo_columns()).where(G.id.in_(ids)))).all()
    return {r.geo_id: r for r in rows}


def metrics_of(row) -> dict | None:
    if row is None:
        return None
    return {name: getattr(row, name) for name in METRIC_FIELDS}


def point_of(lon, lat) -> dict | None:
    return None if lon is None or lat is None else {"lon": lon, "lat": lat}


def computed_of(row) -> dict:
    # the three fields of SegmentRead that are not columns of the segment
    return {
        "metrics": metrics_of(row),
        "start_point": point_of(getattr(row, "start_lon", None), getattr(row, "start_lat", None)),
        "end_point": point_of(getattr(row, "end_lon", None), getattr(row, "end_lat", None)),
    }


def read_dict(segment, row) -> dict:
    # a SegmentRead as a dict: the columns of the segment plus the computed fields
    data = {name: getattr(segment, name) for name in SegmentRead.model_fields if name not in COMPUTED}
    data.update(computed_of(row))
    return data
