# Standard library
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GpxPoint:
    lat: float
    lon: float
    ele: float | None = None
    time: datetime | None = None
    hr: int | None = None
    cad: int | None = None


@dataclass
class ParsedGpx:
    segments: list[list[GpxPoint]]
    sport_hint: str | None = None
    creator: str | None = None
    warnings: set[str] = field(default_factory=set)


@dataclass
class CleanedGpx:
    segments: list[list[GpxPoint]]
    warnings: set[str] = field(default_factory=set)


@dataclass
class GeoMetrics:
    distance_m: int
    elevation_gain_m: int | None = None
    elevation_loss_m: int | None = None
    highest_elevation_m: int | None = None
    lowest_elevation_m: int | None = None
    elevation: int | None = None
    avg_grade: float | None = None
    highest_grade: float | None = None
    total_points: int = 0
    start_lat: float = 0.0
    start_lon: float = 0.0
    end_lat: float = 0.0
    end_lon: float = 0.0


@dataclass
class PerfMetrics:
    started_at: datetime | None = None
    ended_at: datetime | None = None
    total_time_s: int = 0
    moving_time_s: int = 0
    stop_time_s: int = 0
    moving_ratio: float = 0.0
    avg_speed_kmh: float | None = None
    moving_avg_speed_kmh: float | None = None
    ascent_avg_speed_kmh: float | None = None
    descent_avg_speed_kmh: float | None = None
    max_speed_kmh: float | None = None
    max_ascent_speed_kmh: float | None = None
    max_descent_speed_kmh: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    min_heart_rate: int | None = None
    heart_graph: list | None = None
    speed_pattern: list | None = None


@dataclass
class ProcessedGpx:
    geo: GeoMetrics
    performance: PerfMetrics | None = None
    geojson: dict | None = None
    elevation_graph: list | None = None
    route_ewkt: str | None = None
    recorded_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)
    sport_hint: str | None = None
    processor_version: int = 1
