# Standard library
import math
from datetime import datetime, timedelta, timezone

# Third-party
import pytest

# Local application
from app.explorer.services.gpx.matching import nearest_visit
from app.explorer.services.gpx.models import CleanedGpx, GpxPoint


def _make_segment(n=50, step_m=10):
    dlat = step_m / 110540
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    return [
        GpxPoint(
            lat=47.0 + i * dlat,
            lon=11.0,
            ele=1000.0,
            time=t0 + timedelta(seconds=i * 3),
        )
        for i in range(n)
    ]


def test_nearest_visit_on_track():
    seg = _make_segment(n=50, step_m=10)
    mid = seg[25]
    cleaned = CleanedGpx(segments=[seg])
    result = nearest_visit(cleaned, mid.lat, mid.lon)
    assert result.distance_m < 1.0
    assert result.along_track_m is not None
    assert result.along_track_m > 0


def test_nearest_visit_outside_radius():
    seg = _make_segment(n=50, step_m=10)
    cleaned = CleanedGpx(segments=[seg])
    result = nearest_visit(cleaned, 48.0, 12.0)
    assert result.distance_m > 100_000


def test_nearest_visit_time_interpolation():
    seg = _make_segment(n=50, step_m=10)
    mid_lat = (seg[24].lat + seg[25].lat) / 2
    mid_lon = (seg[24].lon + seg[25].lon) / 2
    cleaned = CleanedGpx(segments=[seg])
    result = nearest_visit(cleaned, mid_lat, mid_lon)
    assert result.time is not None
    expected = seg[24].time + (seg[25].time - seg[24].time) / 2
    diff = abs((result.time - expected).total_seconds())
    assert diff < 2.0


def test_nearest_visit_edge_projection():
    seg = _make_segment(n=50, step_m=10)
    offset_lon = 11.0 + 5 / (111320 * math.cos(math.radians(47.0)))
    mid_lat = seg[25].lat
    cleaned = CleanedGpx(segments=[seg])
    result = nearest_visit(cleaned, mid_lat, offset_lon)
    assert result.distance_m < 6.0


def test_nearest_visit_no_timestamps():
    seg = [
        GpxPoint(lat=47.0 + i * (10 / 110540), lon=11.0, ele=1000.0)
        for i in range(50)
    ]
    mid = seg[25]
    cleaned = CleanedGpx(segments=[seg])
    result = nearest_visit(cleaned, mid.lat, mid.lon)
    assert result.time is None
    assert result.along_track_m is not None
