# Standard library
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Third-party
import pytest

# Local application
from app.explorer.services.gpx.errors import GpxProcessingError
from app.explorer.services.gpx.limits import GpxLimits
from app.explorer.services.gpx.pipeline import process_gpx_file
from tests.gpx_factory import climb, make_gpx, save_gpx, straight_line

LIMITS = GpxLimits()


# 1. A 1 km straight line gives ~1000 m distance
def test_straight_line_distance(tmp_dir):
    pts, times, eles = straight_line(n=101, step_m=10)
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert abs(result.geo.distance_m - 1000) < 10


# 2. Flat ground with noise gives gain near 0
def test_flat_ground_no_gain(tmp_dir):
    import random

    rng = random.Random(42)
    pts, times, _ = straight_line(n=200, step_m=5)
    eles = [1000 + rng.gauss(0, 1) for _ in range(200)]
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert result.geo.elevation_gain_m is not None
    assert result.geo.elevation_gain_m < 10


# 3. A 100 m climb gives gain ~100
def test_climb_gain(tmp_dir):
    pts, times, eles = climb(n=200, gain=100, noise_std=0.5)
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert result.geo.elevation_gain_m is not None
    assert abs(result.geo.elevation_gain_m - 100) < 5


# 4. A 5 km jump is removed as outlier
def test_outlier_removal(tmp_dir):
    pts, times, eles = straight_line(n=10, step_m=10)
    pts_list = list(pts)
    pts_list.insert(5, (47.05, 11.0))  # ~5 km jump
    times_list = list(times)
    times_list.insert(
        5, times[4] + timedelta(seconds=1)
    )
    eles_list = list(eles)
    eles_list.insert(5, 1000.0)
    gpx = make_gpx(pts_list, times=times_list, elevations=eles_list)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert "outliers_removed" in result.warnings


# 5. A 10 min gap with 300 m jump splits the segment
def test_gap_splits(tmp_dir):
    pts1, times1, eles1 = straight_line(n=20, step_m=10)
    pts2 = [(47.003, 11.0 + i * 0.0001) for i in range(20)]
    t_gap = times1[-1] + timedelta(minutes=10)
    times2 = [t_gap + timedelta(seconds=i * 3) for i in range(20)]
    eles2 = [1000.0] * 20
    gpx = make_gpx(
        list(pts1) + pts2,
        times=list(times1) + times2,
        elevations=list(eles1) + eles2,
    )
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert "segments_split" in result.warnings
    assert result.performance is not None
    gap_seconds = (t_gap - times1[-1]).total_seconds()
    assert result.performance.total_time_s < gap_seconds


# 6. No timestamps gives no performance
def test_no_timestamps(tmp_dir):
    pts, _, eles = straight_line(n=50)
    gpx = make_gpx(pts, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert result.performance is None
    assert "no_timestamps" in result.warnings


# 7. No elevation gives NULL elevation fields
def test_no_elevation(tmp_dir):
    pts, times, _ = straight_line(n=50)
    gpx = make_gpx(pts, times=times)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert result.geo.elevation_gain_m is None
    assert result.geo.highest_elevation_m is None
    assert "no_elevation" in result.warnings


# 8. Multiple <trk> elements are merged
def test_multi_track_merge(tmp_dir):
    pts, times, eles = straight_line(n=40, step_m=10)
    gpx = make_gpx(pts, times=times, elevations=eles, tracks=2)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert result.geo.distance_m > 0


# 9. Route-only file is accepted
def test_route_only(tmp_dir):
    pts, _, eles = straight_line(n=30)
    gpx = make_gpx(pts, elevations=eles, route_only=True)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert "route_only" in result.warnings


# 10. 50000 input points give bounded output
def test_large_file_bounds(tmp_dir):
    n = 50000
    dlat = 1 / 110540
    pts = [(47.0 + i * dlat, 11.0) for i in range(n)]
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    times = [t0 + timedelta(seconds=i) for i in range(n)]
    eles = [1000.0 + (i % 100) * 0.5 for i in range(n)]
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)

    gj = result.geojson
    if gj["type"] == "LineString":
        assert len(gj["coordinates"]) <= LIMITS.geojson_max_points
    else:
        total = sum(len(c) for c in gj["coordinates"])
        assert total <= LIMITS.geojson_max_points

    if result.elevation_graph:
        assert len(result.elevation_graph) <= LIMITS.graph_max_points
    if result.performance and result.performance.speed_pattern:
        assert len(result.performance.speed_pattern) <= LIMITS.graph_max_points


# 11. Route simplification stays within tolerance
def test_route_simplification_tolerance(tmp_dir):
    from shapely import wkt as shapely_wkt

    pts, times, eles = straight_line(n=200, step_m=5)
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    ewkt = result.route_ewkt
    wkt_str = ewkt.split(";", 1)[1]
    simplified = shapely_wkt.loads(wkt_str)

    from shapely.geometry import LineString

    original = LineString([(p[1], p[0]) for p in pts])
    cos_lat = math.cos(math.radians(47.0))
    for coord in simplified.geoms[0].coords:
        lon, lat = coord
        min_d = min(
            math.sqrt(
                ((lon - p[1]) * cos_lat * 111320) ** 2
                + ((lat - p[0]) * 110540) ** 2
            )
            for p in pts
        )
        assert min_d <= LIMITS.route_simplify_tolerance_m * 1.01


# 12. Heart rate from gpxtpx:hr
def test_heart_rate_parsing(tmp_dir):
    pts, times, eles = straight_line(n=20)
    hr = [120 + i for i in range(20)]
    gpx = make_gpx(pts, times=times, elevations=eles, hr=hr)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert result.performance is not None
    assert result.performance.avg_heart_rate is not None
    assert result.performance.avg_heart_rate > 0


# 13. Empty/invalid file raises GpxProcessingError
def test_empty_file_raises(tmp_dir):
    path = save_gpx("", tmp_dir)
    with pytest.raises(GpxProcessingError):
        process_gpx_file(path, LIMITS)


def test_invalid_xml_raises(tmp_dir):
    path = save_gpx("<html><body>Not GPX</body></html>", tmp_dir)
    with pytest.raises(GpxProcessingError) as exc_info:
        process_gpx_file(path, LIMITS)
    assert exc_info.value.code == "invalid_xml"


# 14. DTD attack raises invalid_xml
def test_dtd_attack(tmp_dir):
    content = '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "test">]><gpx></gpx>'
    path = save_gpx(content, tmp_dir)
    with pytest.raises(GpxProcessingError) as exc_info:
        process_gpx_file(path, LIMITS)
    assert exc_info.value.code == "invalid_xml"


# 15. Non-gpx root raises invalid_xml
def test_non_gpx_root(tmp_dir):
    content = '<?xml version="1.0"?><kml><Document/></kml>'
    path = save_gpx(content, tmp_dir)
    with pytest.raises(GpxProcessingError) as exc_info:
        process_gpx_file(path, LIMITS)
    assert exc_info.value.code == "invalid_xml"


# 16. Naive timestamps as UTC; 1970 is implausible
def test_naive_timestamp_utc(tmp_dir):
    pts = [(47.0 + i * 0.0001, 11.0) for i in range(10)]
    t0 = datetime(2024, 6, 1, 8, 0, 0)  # naive
    times = [t0 + timedelta(seconds=i * 10) for i in range(10)]
    eles = [1000.0] * 10
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert result.performance is not None
    assert result.performance.started_at.tzinfo is not None


def test_implausible_1970_timestamp(tmp_dir):
    pts = [(47.0 + i * 0.0001, 11.0) for i in range(10)]
    t0 = datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    times = [t0 + timedelta(seconds=i * 10) for i in range(10)]
    eles = [1000.0] * 10
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert "implausible_timestamps" in result.warnings
    assert "no_timestamps" in result.warnings


# 17. Waypoints add waypoints_ignored
def test_waypoints_warning(tmp_dir):
    pts, times, eles = straight_line(n=20)
    gpx = make_gpx(pts, times=times, elevations=eles, waypoints=True)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    assert "waypoints_ignored" in result.warnings


# 18. Output is JSON-safe
def test_json_safe(tmp_dir):
    pts, times, eles = climb(n=100, gain=50)
    gpx = make_gpx(pts, times=times, elevations=eles)
    path = save_gpx(gpx, tmp_dir)
    result = process_gpx_file(path, LIMITS)
    json.dumps(result.geojson, allow_nan=False)
    if result.elevation_graph:
        json.dumps(result.elevation_graph, allow_nan=False)
    if result.performance:
        if result.performance.heart_graph:
            json.dumps(result.performance.heart_graph, allow_nan=False)
        if result.performance.speed_pattern:
            json.dumps(result.performance.speed_pattern, allow_nan=False)


# 19. File missing
def test_file_missing():
    with pytest.raises(GpxProcessingError) as exc_info:
        process_gpx_file("/nonexistent/file.gpx", LIMITS)
    assert exc_info.value.code == "file_missing"
