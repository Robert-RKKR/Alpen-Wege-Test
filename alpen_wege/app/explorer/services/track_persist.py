# Standard library
import logging
from datetime import datetime, timezone
from uuid import UUID

# Third-party
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, update
from sqlalchemy.orm import Session

# Local application
from app.explorer.models.models_sub.geo_performance import ExplorerSubGeoPerformance
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.services.gpx.models import ProcessedGpx
from app.explorer.services.sport_inference import infer_sport_type_id
from app.management.jobs.events import publish_job_event
from app.management.jobs.kinds import JobKind
from app.management.jobs.service import fail_active_job_for_subject

logger = logging.getLogger(__name__)


def persist_processed_track(
    session: Session,
    track: ExplorerAggTrack,
    processed: ProcessedGpx,
    existing_geo_record: ExplorerSubGeoRecord | None = None,
) -> ExplorerSubGeoRecord:
    perf_id = None

    if processed.performance is not None:
        p = processed.performance
        if existing_geo_record and existing_geo_record.geo_performance_id:
            perf = session.get(
                ExplorerSubGeoPerformance, existing_geo_record.geo_performance_id
            )
            if perf:
                _set_performance_fields(perf, p)
                perf.updated_at = func.now()
                perf_id = perf.id
        if perf_id is None:
            perf = ExplorerSubGeoPerformance()
            _set_performance_fields(perf, p)
            session.add(perf)
            session.flush()
            perf_id = perf.id
    elif existing_geo_record and existing_geo_record.geo_performance_id:
        perf = session.get(
            ExplorerSubGeoPerformance, existing_geo_record.geo_performance_id
        )
        if perf:
            _clear_performance_fields(perf)
            perf.updated_at = func.now()
            perf_id = perf.id

    geo = processed.geo

    if existing_geo_record:
        rec = existing_geo_record
    else:
        rec = ExplorerSubGeoRecord()
        session.add(rec)

    rec.gpx_id = track.gpx_id
    rec.geo_performance_id = perf_id
    rec.geojson = processed.geojson
    rec.elevation_graph = processed.elevation_graph
    rec.track_types = None
    rec.elevation = _int_or_none(geo.elevation)
    rec.total_points = geo.total_points
    rec.distance_m = _int_or_none(geo.distance_m)
    rec.elevation_gain_m = _int_or_none(geo.elevation_gain_m)
    rec.elevation_loss_m = _int_or_none(geo.elevation_loss_m)
    rec.highest_elevation_m = _int_or_none(geo.highest_elevation_m)
    rec.lowest_elevation_m = _int_or_none(geo.lowest_elevation_m)
    rec.avg_grade = _native(geo.avg_grade)
    rec.highest_grade = _native(geo.highest_grade)
    rec.processor_version = processed.processor_version

    if geo.start_lat or geo.start_lon:
        rec.start_location = WKTElement(
            f"POINT({geo.start_lon} {geo.start_lat})", srid=4326
        )
    else:
        rec.start_location = None

    if geo.end_lat or geo.end_lon:
        rec.end_location = WKTElement(
            f"POINT({geo.end_lon} {geo.end_lat})", srid=4326
        )
    else:
        rec.end_location = None

    if processed.route_ewkt:
        rec.route = func.ST_GeogFromText(processed.route_ewkt)
    else:
        rec.route = None

    if existing_geo_record:
        rec.updated_at = func.now()

    session.flush()

    track.geo_record_id = rec.id
    track.recorded_at = processed.recorded_at
    track.processing_warnings = processed.warnings or None
    track.processed_at = datetime.now(timezone.utc)
    track.processing_status = "ready"
    track.processing_error = None
    track.processing_started_at = None

    if track.sport_type_id is None and processed.sport_hint:
        track.sport_type_id = infer_sport_type_id(session, processed.sport_hint)

    session.flush()
    return rec


def mark_failed(session: Session, track_id: UUID, message: str) -> None:
    result = session.execute(
        update(ExplorerAggTrack)
        .where(
            ExplorerAggTrack.id == track_id,
            ExplorerAggTrack.processing_status == "processing",
        )
        .values(
            processing_status="failed",
            processing_error=message,
            processing_started_at=None,
            updated_at=func.now(),
        )
    )
    job = None
    if result.rowcount:
        # same transaction: the job text equals the track's processing_error
        job = fail_active_job_for_subject(
            session, kind=JobKind.TRACK_PROCESS, subject_type="track",
            subject_id=track_id, message=message,
        )
    session.commit()
    if job is not None:
        publish_job_event(job)


def _native(val):
    if val is None:
        return None
    import numpy as np
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    return val


def _set_performance_fields(perf, p):
    perf.started_at = p.started_at
    perf.ended_at = p.ended_at
    perf.total_time_s = _native(p.total_time_s)
    perf.moving_time_s = _native(p.moving_time_s)
    perf.stop_time_s = _native(p.stop_time_s)
    perf.moving_ratio = _native(p.moving_ratio)
    perf.avg_speed_kmh = _native(p.avg_speed_kmh)
    perf.moving_avg_speed_kmh = _native(p.moving_avg_speed_kmh)
    perf.ascent_avg_speed_kmh = _native(p.ascent_avg_speed_kmh)
    perf.descent_avg_speed_kmh = _native(p.descent_avg_speed_kmh)
    perf.max_speed_kmh = _native(p.max_speed_kmh)
    perf.max_ascent_speed_kmh = _native(p.max_ascent_speed_kmh)
    perf.max_descent_speed_kmh = _native(p.max_descent_speed_kmh)
    perf.avg_heart_rate = _native(p.avg_heart_rate)
    perf.max_heart_rate = _native(p.max_heart_rate)
    perf.min_heart_rate = _native(p.min_heart_rate)
    perf.calories_burned = None
    perf.steps_count = None
    perf.heart_graph = p.heart_graph
    perf.speed_pattern = p.speed_pattern


def _clear_performance_fields(perf):
    for attr in (
        "started_at", "ended_at", "total_time_s", "moving_time_s",
        "stop_time_s", "moving_ratio", "avg_speed_kmh",
        "moving_avg_speed_kmh", "ascent_avg_speed_kmh",
        "descent_avg_speed_kmh", "max_speed_kmh", "max_ascent_speed_kmh",
        "max_descent_speed_kmh", "avg_heart_rate", "max_heart_rate",
        "min_heart_rate", "calories_burned", "steps_count",
        "heart_graph", "speed_pattern",
    ):
        setattr(perf, attr, None)


def _int_or_none(val):
    if val is None:
        return None
    return int(round(val))
