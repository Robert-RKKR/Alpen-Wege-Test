# Standard library
import math
from dataclasses import replace
from pathlib import Path

# Local application
from app.explorer.services.gpx.cleaning import clean, haversine
from app.explorer.services.gpx.errors import GpxProcessingError
from app.explorer.services.gpx.limits import GpxLimits
from app.explorer.services.gpx.models import CleanedGpx, GpxPoint, ParsedGpx, ProcessedGpx
from app.explorer.services.gpx.parser import parse_gpx
from app.explorer.services.gpx.pipeline import load_clean_segments, process_cleaned

# These functions are plain blocking code (parsing and numpy): the routes call them with run_in_threadpool.
# Every result is a ProcessedGpx without performance: a segment is a planned trail, not a recording.


ELEVATION_MIN_M, ELEVATION_MAX_M = -1000.0, 10000.0   # below the Dead Sea shore and above Everest: anything else is a broken value


def sanitize_elevation(cleaned: CleanedGpx) -> CleanedGpx:
    # A file can carry nonsense elevations (a "no data" marker such as -32768, or 1e10). They would ruin the totals, so such
    # a point loses its elevation (the point stays) and the result gets the warning elevation_outliers_dropped.
    dropped = False
    segments = []
    for seg in cleaned.segments:
        points = []
        for p in seg:
            if p.ele is not None and not (ELEVATION_MIN_M <= p.ele <= ELEVATION_MAX_M):   # NaN fails this test too
                p = replace(p, ele=None)
                dropped = True
            points.append(p)
        segments.append(points)
    warnings = set(cleaned.warnings) | ({"elevation_outliers_dropped"} if dropped else set())
    return CleanedGpx(segments=segments, warnings=warnings)


def from_gpx_file(path: str | Path, limits: GpxLimits | None = None) -> ProcessedGpx:
    # An uploaded GPX file. Parsed and cleaned like a track (outliers are removed with the help of the times), then
    # time, heart rate and cadence are dropped.
    limits = limits or GpxLimits.from_settings()
    cleaned = sanitize_elevation(clean(parse_gpx(str(path), limits), limits))
    return process_cleaned(cleaned, limits, planned=True)


def from_coordinates(coordinates: list[list[float]], limits: GpxLimits | None = None) -> ProcessedGpx:
    # Points drawn on a map: [[lon, lat], ...] or [[lon, lat, ele], ...]
    limits = limits or GpxLimits.from_settings()
    points: list[GpxPoint] = []
    for i, c in enumerate(coordinates):
        if not isinstance(c, (list, tuple)) or len(c) not in (2, 3):
            raise GpxProcessingError("bad_coordinates", f"Point {i} must be [lon, lat] or [lon, lat, ele].")
        lon, lat = c[0], c[1]
        ele = c[2] if len(c) == 3 else None
        for value in (lon, lat, ele):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise GpxProcessingError("bad_coordinates", f"Point {i} has a value that is not a number.")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise GpxProcessingError("bad_coordinates", f"Point {i} is outside longitude -180..180 / latitude -90..90.")
        if ele is not None and not ELEVATION_MIN_M <= ele <= ELEVATION_MAX_M:
            raise GpxProcessingError("bad_coordinates", f"Point {i} has an elevation outside {ELEVATION_MIN_M:.0f}..{ELEVATION_MAX_M:.0f} m.")
        points.append(GpxPoint(lat=float(lat), lon=float(lon), ele=None if ele is None else float(ele)))
    cleaned = clean(ParsedGpx(segments=[points]), limits)
    return process_cleaned(cleaned, limits, planned=True)


def track_length_m(cleaned: CleanedGpx) -> float:
    return sum(
        haversine(a.lat, a.lon, b.lat, b.lon)
        for seg in cleaned.segments for a, b in zip(seg, seg[1:])
    )


def clip_by_distance(cleaned: CleanedGpx, start_m: float, end_m: float) -> CleanedGpx:
    # The points whose distance from the start of the track (along the cleaned path, gaps between parts not counted,
    # the same distance as the track's distance_m) lies in [start_m, end_m]
    if not 0 <= start_m < end_m:
        raise GpxProcessingError("bad_range", "start_distance_m must be 0 or more and less than end_distance_m.")
    total = track_length_m(cleaned)
    if start_m >= total:
        raise GpxProcessingError("bad_range", f"start_distance_m is behind the end of the track ({total:.0f} m).")
    run = 0.0
    parts: list[list[GpxPoint]] = []
    for seg in cleaned.segments:
        kept: list[GpxPoint] = []
        prev = None
        for p in seg:
            if prev is not None:
                run += haversine(prev.lat, prev.lon, p.lat, p.lon)
            prev = p
            if start_m <= run <= end_m:
                kept.append(p)
        if len(kept) >= 2:
            parts.append(kept)
    if not parts:
        raise GpxProcessingError("no_usable_path", "The selected part of the track has no usable path.")
    return CleanedGpx(segments=parts, warnings=set(cleaned.warnings))


def load_track(path: str | Path, limits: GpxLimits | None = None) -> CleanedGpx:
    # The cleaned points of a stored track file; read once when several parts are cut from the same track
    return load_clean_segments(path, limits or GpxLimits.from_settings())


def from_cleaned_clip(cleaned: CleanedGpx, start_m: float, end_m: float, limits: GpxLimits | None = None) -> ProcessedGpx:
    limits = limits or GpxLimits.from_settings()
    clipped = sanitize_elevation(clip_by_distance(cleaned, start_m, end_m))
    return process_cleaned(clipped, limits, planned=True)


def from_track_file(path: str | Path, start_m: float, end_m: float, limits: GpxLimits | None = None) -> ProcessedGpx:
    # A part of a recorded track, cut by distance from its start
    limits = limits or GpxLimits.from_settings()
    return from_cleaned_clip(load_track(path, limits), start_m, end_m, limits)
