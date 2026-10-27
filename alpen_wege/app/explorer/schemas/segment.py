from datetime import datetime
from uuid import UUID

from app.config import get_settings

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.compendium.schemas.poi import PoiDetail
from app.core.schemas.ref import DifficultySportDetail, RefRankedDetail, RefWithFactorDetail
from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser


class Point(BaseModel):
    lon: float
    lat: float


class SegmentMetrics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    distance_m: int | None = None
    elevation_gain_m: int | None = None
    elevation_loss_m: int | None = None
    highest_elevation_m: int | None = None
    lowest_elevation_m: int | None = None
    avg_grade: float | None = None
    highest_grade: float | None = None
    total_points: int | None = None


class SegmentFields(BaseModel):
    # What a client sends about a new segment, whatever the way its geometry comes in
    name: str = Field(min_length=1, max_length=255)
    sport_type_id: UUID
    summary: str | None = Field(None, max_length=1000)
    description: str | None = Field(None, max_length=10000)
    name_de: str | None = None
    name_pl: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description_de: str | None = None
    description_pl: str | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    start_poi_id: UUID | None = Field(None, description="Leave out to use the closest POI to the start point.")
    end_poi_id: UUID | None = Field(None, description="Leave out to use the closest POI to the end point.")
    is_public: bool = Field(False, description="New segments are private unless you say otherwise.")


class SegmentFromCoordinates(SegmentFields):
    coordinates: list[list[float]] = Field(
        min_length=2, max_length=get_settings().SEGMENT_DRAW_MAX_POINTS,
        description="Points of the trail in order: [lon, lat] or [lon, lat, elevation_m]. At least 2 and at most "
                    "SEGMENT_DRAW_MAX_POINTS (5000) points.",
    )


class SegmentFromTrack(SegmentFields):
    track_id: UUID = Field(description="One of your own recorded tracks (an administrator may use any).")
    start_distance_m: int = Field(ge=0, description="Where the part starts, in metres from the start of the track.")
    end_distance_m: int = Field(gt=0, description="Where the part ends, in metres from the start of the track.")


class SegmentUpdate(BaseModel):
    # Metadata only. The geometry of a segment never changes: draw a new segment instead.
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = Field(None, max_length=1000)
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = Field(None, max_length=10000)
    description_de: str | None = None
    description_pl: str | None = None
    is_public: bool | None = None
    sport_type_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    start_poi_id: UUID | None = None
    end_poi_id: UUID | None = None

    @field_validator("name", "is_public", "sport_type_id", mode="before")
    @classmethod
    def reject_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None = None
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = None
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = None
    description_de: str | None = None
    description_pl: str | None = None
    is_public: bool
    sport_type_id: UUID
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    start_poi_id: UUID | None = None
    end_poi_id: UUID | None = None
    geo_record_id: UUID
    rating_avg: float | None = None
    rating_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: UUID
    metrics: SegmentMetrics | None = None
    start_point: Point | None = None
    end_point: Point | None = None


class SegmentDetail(SegmentRead):
    sport_type: RefWithFactorDetail | None = Link()
    difficulty_level: RefRankedDetail | None = Link()
    difficulty_sport: DifficultySportDetail | None = Link()
    start_poi: PoiDetail | None = Link()
    end_poi: PoiDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")


class SegmentCreated(SegmentRead):
    warnings: list[str] = Field(default_factory=list, description="Notes from reading the geometry, for example no_elevation.")


class SegmentGeometry(BaseModel):
    geojson: dict | None = None
    elevation_graph: list | None = None
    start_location: dict | None = None
    end_location: dict | None = None
