# Standard library
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

# Third-party
import pytest

# Local application
from app.explorer.services import segment_build as sb
from app.explorer.services.gpx.cleaning import haversine
from app.explorer.services.gpx.errors import GpxProcessingError
from app.explorer.services.gpx.limits import GpxLimits
from app.explorer.services.gpx.models import CleanedGpx, GpxPoint
from app.explorer.services.gpx.pipeline import process_cleaned, process_gpx_file, strip_time_data
from tests.gpx_factory import make_gpx

LIMITS = GpxLimits()
DLAT = 25 / 110540


def line(n=60, ele0=1000.0, climb=0.5):
    return [[11.0, 47.0 + i * DLAT, ele0 + i * climb] for i in range(n)]


def timed_points(n=60):
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    return [GpxPoint(lat=47.0 + i * DLAT, lon=11.0, ele=1000.0 + i * 0.5, time=t0 + timedelta(seconds=5 * i), hr=120 + i % 10, cad=70) for i in range(n)]


def write_gpx(tmp_path, n=60, timed=True, hr=True):
    pts = [(47.0 + i * DLAT, 11.0) for i in range(n)]
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    text = make_gpx(pts, times=[t0 + timedelta(seconds=5 * i) for i in range(n)] if timed else None,
                    elevations=[1000.0 + i * 0.5 for i in range(n)], hr=[130 + i % 10 for i in range(n)] if hr and timed else None)
    path = tmp_path / "t.gpx"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ planned: no time data, ever
def test_strip_time_data_removes_time_hr_and_cadence_and_keeps_the_place():
    cleaned = CleanedGpx(segments=[timed_points(5)], warnings={"x"})
    stripped = strip_time_data(cleaned)
    assert all(p.time is None and p.hr is None and p.cad is None for p in stripped.segments[0])
    assert [(p.lat, p.lon, p.ele) for p in stripped.segments[0]] == [(p.lat, p.lon, p.ele) for p in cleaned.segments[0]]
    assert cleaned.segments[0][0].time is not None and stripped.warnings == {"x"}              # the original is untouched


def test_a_planned_result_has_no_performance_and_no_timestamp_warning():
    cleaned = CleanedGpx(segments=[timed_points(60)])
    planned = process_cleaned(cleaned, LIMITS, planned=True)
    assert planned.performance is None and planned.recorded_at is None and "no_timestamps" not in planned.warnings
    recorded = process_cleaned(cleaned, LIMITS)
    assert recorded.performance is not None and recorded.recorded_at is not None             # a track keeps its time data
    assert planned.geo == recorded.geo                                                        # the geometry is the same


def test_a_gpx_file_with_times_and_heart_rate_gives_a_segment_without_them(tmp_path):
    result = sb.from_gpx_file(write_gpx(tmp_path), LIMITS)
    assert result.performance is None and result.recorded_at is None
    assert result.geo.distance_m == pytest.approx(59 * 25, rel=0.02) and result.geo.elevation_gain_m is not None
    assert result.geojson["type"] == "LineString" and result.route_ewkt.startswith("SRID=4326;MULTILINESTRING")


def test_process_gpx_file_is_still_the_track_pipeline(tmp_path):
    path = write_gpx(tmp_path)
    track = process_gpx_file(path, LIMITS)
    assert track.performance is not None and track.performance.avg_heart_rate is not None and track.recorded_at is not None


# ------------------------------------------------------------------ drawn points
def test_drawn_points_give_a_planned_result():
    result = sb.from_coordinates(line(40), LIMITS)
    assert result.performance is None and result.geo.distance_m == pytest.approx(39 * 25, rel=0.02)
    assert result.geo.start_lon == 11.0 and result.geo.start_lat == pytest.approx(47.0) and result.geo.end_lat == pytest.approx(47.0 + 39 * DLAT)


def test_drawn_points_without_elevation_are_fine():
    result = sb.from_coordinates([c[:2] for c in line(40)], LIMITS)
    assert result.geo.elevation_gain_m is None and "no_elevation" in result.warnings and result.elevation_graph is None


@pytest.mark.parametrize("points,fragment", [
    ([[11.0, 47.0, 1, 2], [11.0, 47.1]], "[lon, lat]"),
    ([[11.0], [11.0, 47.1]], "[lon, lat]"),
    ([[11.0, 47.0], [11.0, "x"]], "not a number"),
    ([[11.0, 47.0], [11.0, math.nan]], "not a number"),
    ([[11.0, 47.0], [11.0, math.inf]], "not a number"),
    ([[11.0, 47.0], [True, 47.1]], "not a number"),
    ([[11.0, 47.0], [11.0, 95.0]], "outside"),
    ([[11.0, 47.0], [181.0, 47.0]], "outside"),
    ([[11.0, 47.0, "high"], [11.0, 47.1]], "not a number"),
])
def test_bad_points_are_refused_with_a_message(points, fragment):
    with pytest.raises(GpxProcessingError) as excinfo:
        sb.from_coordinates(points, LIMITS)
    assert excinfo.value.code == "bad_coordinates" and fragment in excinfo.value.user_message


def test_points_that_make_no_path_are_refused():
    with pytest.raises(GpxProcessingError) as excinfo:
        sb.from_coordinates([[11.0, 47.0], [11.0, 47.0]], LIMITS)
    assert excinfo.value.code == "no_usable_path"
    with pytest.raises(GpxProcessingError):
        sb.from_coordinates([[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]], LIMITS)


# ------------------------------------------------------------------ a part of a track
def cleaned_line(n=101):
    return CleanedGpx(segments=[timed_points(n)])


def test_the_track_length_is_the_sum_of_its_steps():
    assert sb.track_length_m(cleaned_line(101)) == pytest.approx(100 * 25, rel=0.01)


def test_a_clip_keeps_the_points_between_the_two_distances():
    track = cleaned_line(101)
    clipped = sb.clip_by_distance(track, 500, 1500)
    pts = clipped.segments[0]
    step = haversine(47.0, 11.0, 47.0 + DLAT, 11.0)                                      # one step in metres as the code measures it
    along = lambda p: haversine(47.0, 11.0, p.lat, p.lon)                                # distance from the start of the track
    assert 500 <= along(pts[0]) < 500 + step and 1500 - step < along(pts[-1]) <= 1500
    assert len(pts) in (40, 41) and haversine(pts[0].lat, pts[0].lon, pts[-1].lat, pts[-1].lon) == pytest.approx(1000, abs=step)


def test_a_clip_over_two_parts_of_a_track_counts_distance_inside_the_parts_only():
    a = [GpxPoint(lat=47.0 + i * DLAT, lon=11.0) for i in range(11)]                     # 250 m
    b = [GpxPoint(lat=48.0 + i * DLAT, lon=11.0) for i in range(11)]                     # 250 m, 111 km further
    clipped = sb.clip_by_distance(CleanedGpx(segments=[a, b]), 100, 400)
    assert len(clipped.segments) == 2 and clipped.segments[1][0].lat > 47.9


@pytest.mark.parametrize("start,end,fragment", [(500, 500, "start_distance_m"), (900, 100, "start_distance_m"), (-1, 100, "start_distance_m"), (5000, 6000, "behind the end")])
def test_a_bad_range_is_refused(start, end, fragment):
    with pytest.raises(GpxProcessingError) as excinfo:
        sb.clip_by_distance(cleaned_line(101), start, end)
    assert excinfo.value.code == "bad_range" and fragment in excinfo.value.user_message


def test_a_clip_with_fewer_than_two_points_is_refused():
    with pytest.raises(GpxProcessingError) as excinfo:
        sb.clip_by_distance(cleaned_line(101), 100, 110)                                  # 10 m: one point only
    assert excinfo.value.code == "no_usable_path"


def test_a_clip_from_a_track_file_has_no_time_data(tmp_path):
    result = sb.from_track_file(write_gpx(tmp_path, n=200), 500, 2500, LIMITS)
    assert result.performance is None and result.geo.distance_m == pytest.approx(2000, rel=0.03)


# ------------------------------------------------------------------ broken elevations
def test_a_drawn_elevation_outside_the_world_is_refused():
    for ele in (1e10, -5000, 10001):
        with pytest.raises(GpxProcessingError) as excinfo:
            sb.from_coordinates([[11.0, 47.0, ele], [11.0, 47.001, 1000]], LIMITS)
        assert excinfo.value.code == "bad_coordinates" and "elevation" in excinfo.value.user_message
    ok = sb.from_coordinates([[11.0, 47.0, -400], [11.0, 47.001, 8848]], LIMITS)        # the real extremes of the earth are fine
    assert ok.geo.highest_elevation_m is not None and ok.geo.highest_elevation_m > 1000


def test_a_file_with_broken_elevations_loses_only_those_elevations():
    points = timed_points(60)
    points[10] = replace(points[10], ele=-32768.0)        # a "no data" marker
    points[20] = replace(points[20], ele=1e10)
    points[30] = replace(points[30], ele=float("nan"))
    cleaned = sb.sanitize_elevation(CleanedGpx(segments=[points], warnings=set()))
    assert [p.ele for p in cleaned.segments[0] if p.ele is None] == [None, None, None] and len(cleaned.segments[0]) == 60
    assert "elevation_outliers_dropped" in cleaned.warnings
    result = process_cleaned(cleaned, LIMITS, planned=True)
    assert result.geo.highest_elevation_m < 1100 and result.geo.elevation_gain_m < 100       # not ruined by the broken values
    assert "elevation_outliers_dropped" in result.warnings


def test_good_elevations_are_left_alone_and_no_warning_is_added():
    cleaned = sb.sanitize_elevation(CleanedGpx(segments=[timed_points(10)], warnings={"x"}))
    assert [p.ele for p in cleaned.segments[0]] == [p.ele for p in timed_points(10)] and cleaned.warnings == {"x"}


ANTIPODE = (69.51232454868148, 86.5812282599507, -69.51232454868148, 86.5812282599507 - 180)    # a pair where rounding gives a > 1


def test_the_distance_between_opposite_points_is_half_the_earth_even_where_rounding_exceeds_one():
    # On opposite points the haversine term can come out one rounding step above 1. The square root brings that back to 1
    # (measured on 3 million random opposite pairs: no error), and the code clamps it as well, so the answer is the half circumference.
    lat1, lon1, lat2, lon2 = ANTIPODE
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    assert a > 1
    assert haversine(*ANTIPODE) == pytest.approx(math.pi * 6371008.8, rel=1e-6)


def test_the_distance_between_opposite_points_does_not_crash():
    assert haversine(10.0, 0.0, -10.0, 180.0) == pytest.approx(math.pi * 6371008.8, rel=1e-3)
    assert haversine(0.0, 0.0, 0.0, 180.0) == pytest.approx(math.pi * 6371008.8, rel=1e-9)
    assert haversine(47.0, 11.0, 47.0, 11.0) == 0.0


def test_a_track_read_once_can_be_cut_twice(tmp_path):
    cleaned = sb.load_track(write_gpx(tmp_path, n=200), LIMITS)
    first = sb.from_cleaned_clip(cleaned, 0, 1500, LIMITS)
    second = sb.from_cleaned_clip(cleaned, 1500, 3000, LIMITS)
    assert first.performance is None and second.performance is None
    assert first.geo.distance_m == pytest.approx(1500, rel=0.03) and second.geo.distance_m == pytest.approx(1500, rel=0.03)
