# Standard library
import json
from pathlib import Path

# Local application
from .cleaning import clean
from .errors import GpxProcessingError
from .limits import GpxLimits
from .metrics import geometry_metrics, performance_metrics
from .models import CleanedGpx, ProcessedGpx
from .parser import parse_gpx
from .shaping import build_elevation_graph, build_geojson, build_route_ewkt

PROCESSOR_VERSION = 1


def process_gpx_file(
    path: str | Path, limits: GpxLimits | None = None,
) -> ProcessedGpx:
    path = str(path)
    if limits is None:
        limits = GpxLimits.from_settings()

    if not Path(path).exists():
        raise GpxProcessingError(
            "file_missing", "The GPX file could not be found."
        )

    parsed = parse_gpx(path, limits)
    cleaned = clean(parsed, limits)
    warnings = set(cleaned.warnings)

    has_any_time = any(
        p.time is not None for seg in cleaned.segments for p in seg
    )
    has_all_time = all(
        p.time is not None for seg in cleaned.segments for p in seg
    )
    if not has_any_time:
        warnings.add("no_timestamps")
    elif not has_all_time:
        warnings.add("partial_timestamps")

    has_any_ele = any(
        p.ele is not None for seg in cleaned.segments for p in seg
    )
    if not has_any_ele:
        warnings.add("no_elevation")

    geo = geometry_metrics(cleaned, limits)
    perf = performance_metrics(cleaned, geo, limits)

    geojson, gj_warnings = build_geojson(cleaned, limits)
    warnings.update(gj_warnings)
    ele_graph = build_elevation_graph(cleaned, limits)
    route_ewkt = build_route_ewkt(cleaned, limits)

    _validate_json(geojson)
    if ele_graph is not None:
        _validate_json(ele_graph)
    if perf is not None:
        if perf.heart_graph is not None:
            _validate_json(perf.heart_graph)
        if perf.speed_pattern is not None:
            _validate_json(perf.speed_pattern)

    return ProcessedGpx(
        geo=geo,
        performance=perf,
        geojson=geojson,
        elevation_graph=ele_graph,
        route_ewkt=route_ewkt,
        recorded_at=perf.started_at if perf else None,
        warnings=sorted(warnings),
        sport_hint=parsed.sport_hint,
        processor_version=PROCESSOR_VERSION,
    )


def load_clean_segments(
    path: str | Path, limits: GpxLimits | None = None,
) -> CleanedGpx:
    path = str(path)
    if limits is None:
        limits = GpxLimits.from_settings()
    parsed = parse_gpx(path, limits)
    return clean(parsed, limits)


def _validate_json(obj) -> None:
    json.dumps(obj, allow_nan=False)
