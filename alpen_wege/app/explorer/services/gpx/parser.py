# Standard library
from datetime import datetime, timezone

# Third-party
import gpxpy

# Local application
from .errors import GpxProcessingError
from .limits import GpxLimits
from .models import GpxPoint, ParsedGpx
from .xml_guard import check_gpx_root


def _plausible_time(
    dt: datetime | None, min_year: int, max_future_days: int,
) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    if dt.year < min_year:
        return None
    now = datetime.now(timezone.utc)
    from datetime import timedelta

    if dt > now + timedelta(days=max_future_days):
        return None
    return dt


def _parse_hr_cad(point) -> tuple[int | None, int | None]:
    hr = None
    cad = None
    for ext in point.extensions:
        for elem in [ext] + list(ext.iter()):
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local == "hr" and elem.text:
                try:
                    val = int(float(elem.text))
                    if 30 <= val <= 250:
                        hr = val
                except (ValueError, TypeError):
                    pass
            elif local == "cad" and elem.text:
                try:
                    cad = int(float(elem.text))
                except (ValueError, TypeError):
                    pass
    return hr, cad


def parse_gpx(path: str, limits: GpxLimits) -> ParsedGpx:
    check_gpx_root(path)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        try:
            gpx = gpxpy.parse(f)
        except Exception as exc:
            raise GpxProcessingError(
                "invalid_xml", f"Could not parse GPX: {exc}"
            ) from exc

    warnings: set[str] = set()
    sport_hint = None
    creator = gpx.creator

    segments: list[list[GpxPoint]] = []

    for track in gpx.tracks:
        if sport_hint is None and track.type:
            sport_hint = track.type
        for seg in track.segments:
            pts: list[GpxPoint] = []
            for p in seg.points:
                t = _plausible_time(
                    p.time, limits.timestamp_min_year,
                    limits.timestamp_max_future_days,
                )
                if p.time is not None and t is None:
                    warnings.add("implausible_timestamps")
                hr, cad = _parse_hr_cad(p)
                pts.append(GpxPoint(
                    lat=p.latitude, lon=p.longitude,
                    ele=p.elevation, time=t, hr=hr, cad=cad,
                ))
            if pts:
                segments.append(pts)

    if not segments:
        for route in gpx.routes:
            pts = []
            for p in route.points:
                t = _plausible_time(
                    p.time, limits.timestamp_min_year,
                    limits.timestamp_max_future_days,
                )
                if p.time is not None and t is None:
                    warnings.add("implausible_timestamps")
                pts.append(GpxPoint(
                    lat=p.latitude, lon=p.longitude,
                    ele=p.elevation, time=t,
                ))
            if pts:
                segments.append(pts)
        if segments:
            warnings.add("route_only")

    if gpx.waypoints:
        warnings.add("waypoints_ignored")

    if not segments:
        raise GpxProcessingError(
            "no_usable_path", "No usable path found in the file."
        )

    return ParsedGpx(
        segments=segments, sport_hint=sport_hint,
        creator=creator, warnings=warnings,
    )
