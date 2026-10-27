# Third-party
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.config import get_settings
from app.core.models.models_ref import CoreRefDifficultyLevel, CoreRefDifficultySport, CoreRefSportType
from app.core.utils.responses import AppError
from app.explorer.models.models_agg.segment import ExplorerAggSegment
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.services.gpx.models import ProcessedGpx


def _int(val):
    return None if val is None else int(round(val))


def _float(val):
    return None if val is None else float(val)


def geo_record_from(processed: ProcessedGpx) -> ExplorerSubGeoRecord:
    # A new geo record for a segment: no GPX file and no performance row (a planned trail has no time data)
    geo = processed.geo
    rec = ExplorerSubGeoRecord()
    rec.gpx_id = None
    rec.geo_performance_id = None
    rec.geojson = processed.geojson
    rec.elevation_graph = processed.elevation_graph
    rec.track_types = None
    rec.elevation = _int(geo.elevation)
    rec.total_points = geo.total_points
    rec.distance_m = _int(geo.distance_m)
    rec.elevation_gain_m = _int(geo.elevation_gain_m)
    rec.elevation_loss_m = _int(geo.elevation_loss_m)
    rec.highest_elevation_m = _int(geo.highest_elevation_m)
    rec.lowest_elevation_m = _int(geo.lowest_elevation_m)
    rec.avg_grade = _float(geo.avg_grade)
    rec.highest_grade = _float(geo.highest_grade)
    rec.processor_version = processed.processor_version
    rec.start_location = WKTElement(f"POINT({geo.start_lon} {geo.start_lat})", srid=4326)
    rec.end_location = WKTElement(f"POINT({geo.end_lon} {geo.end_lat})", srid=4326)
    rec.route = func.ST_GeogFromText(processed.route_ewkt) if processed.route_ewkt else None
    return rec


async def nearest_poi_id(db: AsyncSession, lon: float, lat: float, radius_m: float | None = None):
    # The closest compendium POI within radius_m of a point, or None (the same rule as the track start and end POI)
    radius = get_settings().POI_COLLECT_RADIUS_M if radius_m is None else radius_m
    row = (await db.execute(
        text(
            "SELECT poi.id FROM compendium_cat_poi poi "
            " WHERE ST_DWithin(poi.location::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r) "
            " ORDER BY ST_Distance(poi.location::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) LIMIT 1"
        ),
        {"lon": lon, "lat": lat, "r": radius},
    )).first()
    return row[0] if row else None


POI_MAX_DISTANCE_M = 500.0     # a POI named by the client may be this far from the start or end of the segment


async def ensure_poi_near(db: AsyncSession, field: str, poi_id, lon: float, lat: float) -> None:
    # Two segments at "the same POI" count as connected whatever their distance, so a POI that is nowhere near the end of the
    # segment must not be accepted.
    if poi_id is None:
        return
    row = (await db.execute(
        text("SELECT ST_Distance(location::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) FROM compendium_cat_poi WHERE id = :id"),
        {"lon": lon, "lat": lat, "id": poi_id},
    )).first()
    if row is not None and row[0] > POI_MAX_DISTANCE_M:     # a POI that does not exist is reported by ensure_refs
        text_ = f"{field}: the POI is {row[0]:.0f} m from that end of the segment; at most {POI_MAX_DISTANCE_M:.0f} m."
        raise AppError(422, "Validation failed", error_message=text_, error_errors=[{"field": field, "code": "poi_too_far", "message": text_}])


async def add_segment(
    db: AsyncSession,
    processed: ProcessedGpx,
    *,
    user_id,
    fields: dict,
) -> ExplorerAggSegment:
    # Creates the geo record and the segment in the caller's transaction (flushed, not committed). fields are the
    # columns of the segment (name, sport_type_id, is_public, ...). Start and end POI are found from the geometry
    # unless the caller named them.
    geo = processed.geo
    await ensure_poi_near(db, "start_poi_id", fields.get("start_poi_id"), geo.start_lon, geo.start_lat)
    await ensure_poi_near(db, "end_poi_id", fields.get("end_poi_id"), geo.end_lon, geo.end_lat)
    rec = geo_record_from(processed)
    db.add(rec)
    await db.flush()
    values = dict(fields)
    if values.get("start_poi_id") is None:
        values["start_poi_id"] = await nearest_poi_id(db, geo.start_lon, geo.start_lat)
    if values.get("end_poi_id") is None:
        values["end_poi_id"] = await nearest_poi_id(db, geo.end_lon, geo.end_lat)
    segment = ExplorerAggSegment(**values, geo_record_id=rec.id, created_by=user_id)
    db.add(segment)
    await db.flush()
    return segment


REFERENCES = {
    "sport_type_id": CoreRefSportType,
    "difficulty_level_id": CoreRefDifficultyLevel,
    "difficulty_sport_id": CoreRefDifficultySport,
    "start_poi_id": CompendiumCatPoi,
    "end_poi_id": CompendiumCatPoi,
}


async def ensure_refs(db: AsyncSession, values: dict) -> None:
    # A named reference that does not exist is a 422 with the field name, not a foreign key error (500) at the commit
    problems = []
    for field, model in REFERENCES.items():
        value = values.get(field)
        if value is not None and await db.get(model, value) is None:
            problems.append({"field": field, "code": "not_found", "message": f"{field}: {value} does not exist."})
    if problems:
        raise AppError(
            422, "Validation failed",
            error_message=f"The request contains {len(problems)} invalid field(s). Check error_errors for details.",
            error_errors=problems,
        )


FIELD_NAMES = (
    "name", "name_de", "name_pl", "summary", "summary_de", "summary_pl", "description", "description_de", "description_pl",
    "sport_type_id", "difficulty_level_id", "difficulty_sport_id", "start_poi_id", "end_poi_id", "is_public",
)


def segment_fields(meta) -> dict:
    # the columns of a new segment from the fields a client sent (a SegmentFields or anything like it)
    return {name: getattr(meta, name) for name in FIELD_NAMES}
