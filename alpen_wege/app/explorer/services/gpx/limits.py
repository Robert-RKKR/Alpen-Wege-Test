# Standard library
from dataclasses import dataclass


@dataclass(frozen=True)
class GpxLimits:
    max_speed_ms: float = 70.0
    max_gap_no_time_m: float = 5000.0
    segment_gap_s: float = 300.0
    segment_gap_min_m: float = 100.0
    moving_speed_ms: float = 0.5
    timestamp_min_year: int = 2000
    timestamp_max_future_days: int = 1
    elevation_median_window: int = 5
    elevation_threshold_m: float = 3.0
    grade_window_m: float = 50.0
    geojson_max_points: int = 1000
    geojson_coord_decimals: int = 5
    graph_max_points: int = 300
    route_simplify_tolerance_m: float = 5.0
    poi_collect_radius_m: float = 50.0

    @classmethod
    def from_settings(cls) -> "GpxLimits":
        from app.config import get_settings

        s = get_settings()
        return cls(
            max_speed_ms=s.GPX_MAX_SPEED_MS,
            max_gap_no_time_m=s.GPX_MAX_GAP_NO_TIME_M,
            segment_gap_s=s.GPX_SEGMENT_GAP_S,
            segment_gap_min_m=s.GPX_SEGMENT_GAP_MIN_M,
            moving_speed_ms=s.GPX_MOVING_SPEED_MS,
            timestamp_min_year=s.GPX_TIMESTAMP_MIN_YEAR,
            timestamp_max_future_days=s.GPX_TIMESTAMP_MAX_FUTURE_DAYS,
            elevation_median_window=s.ELEVATION_MEDIAN_WINDOW,
            elevation_threshold_m=s.ELEVATION_THRESHOLD_M,
            grade_window_m=s.GRADE_WINDOW_M,
            geojson_max_points=s.GEOJSON_MAX_POINTS,
            geojson_coord_decimals=s.GEOJSON_COORD_DECIMALS,
            graph_max_points=s.GRAPH_MAX_POINTS,
            route_simplify_tolerance_m=s.ROUTE_SIMPLIFY_TOLERANCE_M,
            poi_collect_radius_m=s.POI_COLLECT_RADIUS_M,
        )
