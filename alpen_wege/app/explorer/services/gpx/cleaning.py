# Standard library
import math

# Third-party
import numpy as np

# Local application
from .limits import GpxLimits
from .models import CleanedGpx, GpxPoint, ParsedGpx

R_EARTH = 6371008.8


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def haversine_vec(
    lat1: np.ndarray, lon1: np.ndarray,
    lat2: np.ndarray, lon2: np.ndarray,
) -> np.ndarray:
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = (
        np.sin(dphi / 2) ** 2
        + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    )
    return 2 * R_EARTH * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def clean(parsed: ParsedGpx, limits: GpxLimits) -> CleanedGpx:
    warnings = set(parsed.warnings)
    result_segments: list[list[GpxPoint]] = []

    for seg in parsed.segments:
        pts = _clean_segment(seg, limits, warnings)
        result_segments.extend(pts)

    final = [s for s in result_segments if len(s) >= 2]
    if len(final) < len(result_segments):
        warnings.add("isolated_points_dropped")

    if not final:
        from .errors import GpxProcessingError

        raise GpxProcessingError(
            "no_usable_path", "No usable path found in the file."
        )

    return CleanedGpx(segments=final, warnings=warnings)


def _clean_segment(
    pts: list[GpxPoint], limits: GpxLimits, warnings: set[str],
) -> list[list[GpxPoint]]:
    # 1. Drop invalid coordinates
    valid = [
        p for p in pts
        if _valid_coords(p.lat, p.lon)
    ]

    # 2. Drop consecutive duplicates
    deduped: list[GpxPoint] = []
    for p in valid:
        if deduped and deduped[-1].lat == p.lat and deduped[-1].lon == p.lon:
            continue
        deduped.append(p)

    # 3. Outlier removal
    cleaned: list[GpxPoint] = []
    outliers_found = False
    for p in deduped:
        if not cleaned:
            cleaned.append(p)
            continue
        prev = cleaned[-1]
        d = haversine(prev.lat, prev.lon, p.lat, p.lon)
        if prev.time is not None and p.time is not None:
            dt = (p.time - prev.time).total_seconds()
            if dt > 0 and d / dt > limits.max_speed_ms:
                outliers_found = True
                continue
            if dt <= 0 and d > 50:
                outliers_found = True
                continue
        cleaned.append(p)
    if outliers_found:
        warnings.add("outliers_removed")

    # 4. Split at gaps
    sub_segments: list[list[GpxPoint]] = []
    current: list[GpxPoint] = []
    for p in cleaned:
        if not current:
            current.append(p)
            continue
        prev = current[-1]
        d = haversine(prev.lat, prev.lon, p.lat, p.lon)
        should_split = False
        if prev.time is not None and p.time is not None:
            dt = (p.time - prev.time).total_seconds()
            if dt > limits.segment_gap_s and d >= limits.segment_gap_min_m:
                should_split = True
        elif prev.time is None or p.time is None:
            if d > limits.max_gap_no_time_m:
                should_split = True

        if should_split:
            warnings.add("segments_split")
            sub_segments.append(current)
            current = [p]
        else:
            current.append(p)
    if current:
        sub_segments.append(current)

    return sub_segments


def _valid_coords(lat: float, lon: float) -> bool:
    if lat is None or lon is None:
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return False
    return True
