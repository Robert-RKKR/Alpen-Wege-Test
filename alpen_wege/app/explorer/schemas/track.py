from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class TrackCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    processing_status: str
    created_at: datetime
    duplicate_of_track_id: UUID | None = None
    job_id: UUID | None = None


class TrackMetrics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    distance_m: int | None = None
    elevation_gain_m: int | None = None
    elevation_loss_m: int | None = None
    highest_elevation_m: int | None = None
    lowest_elevation_m: int | None = None
    total_time_s: int | None = None
    moving_time_s: int | None = None


class TrackListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    summary: str | None = None
    is_public: bool
    sport_type_id: UUID | None = None
    recorded_at: datetime | None = None
    created_at: datetime
    processing_status: str
    archived_at: datetime | None = None
    created_by: UUID
    metrics: TrackMetrics | None = None


class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None
    is_public: bool
    processing_status: str
    processing_error: str | None = None
    processing_warnings: list[str] | None = None
    processed_at: datetime | None = None
    recorded_at: datetime | None = None
    archived_at: datetime | None = None
    sport_type_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    start_poi_id: UUID | None = None
    end_poi_id: UUID | None = None
    geo_record_id: UUID | None = None
    gpx_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    metrics: TrackMetrics | None = None


class TrackUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None
    is_public: bool | None = None
    sport_type_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    start_poi_id: UUID | None = None
    end_poi_id: UUID | None = None

    @field_validator("name", "is_public", mode="before")
    @classmethod
    def reject_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class TrackGeometry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    geojson: dict | None = None
    elevation_graph: list | None = None
    heart_graph: list | None = None
    speed_pattern: list | None = None
    start_location: dict | None = None
    end_location: dict | None = None


class TrackPerformance(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    started_at: datetime | None = None
    ended_at: datetime | None = None
    total_time_s: int | None = None
    moving_time_s: int | None = None
    stop_time_s: int | None = None
    moving_ratio: float | None = None
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
