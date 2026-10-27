from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import get_settings

from app.core.schemas.ref import DifficultySportDetail, RefRankedDetail, RefWithFactorDetail
from app.core.utils.expand import Link
from app.explorer.schemas.segment import Point, SegmentFields
from app.profile.schemas.user_read import ExpandedUser


# ------------------------------------------------------------------ plan conditions (one row per route, written with the route)

class PlanConditionsFields(BaseModel):
    equipment_required: list[str] | None = None
    equipment_optional: list[str] | None = None
    permit_required: bool | None = None
    permit_info: str | None = None
    permit_info_de: str | None = None
    permit_info_pl: str | None = None
    guide_recommended: bool | None = None
    min_age: int | None = Field(None, ge=0, le=120)
    max_group_size: int | None = Field(None, ge=1, le=10000)
    best_months: list[int] | None = Field(None, description="Month numbers 1 to 12.")
    best_months_note: str | None = None
    best_months_note_de: str | None = None
    best_months_note_pl: str | None = None

    @field_validator("best_months")
    @classmethod
    def months_are_1_to_12(cls, v):
        if v is not None and any(not 1 <= m <= 12 for m in v):
            raise ValueError("best_months must contain numbers from 1 to 12")
        return v


class PlanConditionsInput(PlanConditionsFields):
    model_config = ConfigDict(extra="forbid")


class PlanConditionsRead(PlanConditionsFields):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


# ------------------------------------------------------------------ the segment rows of a route

class InlineSegment(SegmentFields):
    # A new segment that is created while the route is saved: either points drawn on a map or a part of a track
    is_public: bool | None = Field(None, description="Leave out: like the route.")
    coordinates: list[list[float]] | None = Field(None, max_length=get_settings().SEGMENT_DRAW_MAX_POINTS, description="[lon, lat] or [lon, lat, ele] points (drawn on the map).")
    track_id: UUID | None = Field(None, description="Instead of coordinates: one of your own tracks ...")
    start_distance_m: int | None = Field(None, ge=0, description="... from this distance (metres from the start of the track) ...")
    end_distance_m: int | None = Field(None, gt=0, description="... to this distance.")

    @model_validator(mode="after")
    def one_way_in(self):
        if (self.coordinates is None) == (self.track_id is None):
            raise ValueError("send either coordinates or track_id (with start_distance_m and end_distance_m), not both and not neither")
        if self.coordinates is not None:
            if len(self.coordinates) < 2:
                raise ValueError("coordinates needs at least 2 points")
            if self.start_distance_m is not None or self.end_distance_m is not None:
                raise ValueError("start_distance_m and end_distance_m belong to track_id")
        else:
            if self.start_distance_m is None or self.end_distance_m is None:
                raise ValueError("track_id needs start_distance_m and end_distance_m")
            if self.start_distance_m >= self.end_distance_m:
                raise ValueError("start_distance_m must be less than end_distance_m")
        return self


class RouteSegmentIn(BaseModel):
    segment_id: UUID | None = Field(None, description="An existing segment of yours or a public one ...")
    inline: InlineSegment | None = Field(None, description="... or a new segment that is created with this save.")
    slot_position: int = Field(ge=0, description="Place in the route, 0, 1, 2 ... without gaps.")
    alt_group: int | None = Field(None, ge=0, description="Leave out. If sent it must equal slot_position (alternatives share the slot).")
    is_default: bool = Field(True, description="The segment the route normally takes in this slot. Exactly one per slot.")
    is_reversed: bool = Field(False, description="Walk the segment from its end to its start.")

    @model_validator(mode="after")
    def exactly_one_source(self):
        if (self.segment_id is None) == (self.inline is None):
            raise ValueError("send either segment_id or inline, not both and not neither")
        return self


class SetRouteSegments(BaseModel):
    segments: list[RouteSegmentIn] = Field(max_length=200, description="The complete list; it replaces the one that is saved. An empty list empties the route.")
    validation: Literal["strict", "warn"] = Field(
        "strict", description="strict: a gap between segments or alternatives that do not fit is a 422 and nothing is saved. warn: it is saved and reported.")


class ValidateItem(BaseModel):
    # a saved segment, or a drawing that is not saved yet (only its first and last point matter)
    segment_id: UUID | None = None
    start: list[float] | None = Field(None, min_length=2, max_length=2, description="[lon, lat] of an unsaved drawing.")
    end: list[float] | None = Field(None, min_length=2, max_length=2, description="[lon, lat] of an unsaved drawing.")
    slot_position: int = Field(ge=0)
    alt_group: int | None = Field(None, ge=0)
    is_default: bool = True
    is_reversed: bool = False

    @model_validator(mode="after")
    def saved_or_drawn(self):
        if self.segment_id is None and (self.start is None or self.end is None):
            raise ValueError("send segment_id, or start and end of an unsaved drawing")
        if self.segment_id is not None and (self.start is not None or self.end is not None):
            raise ValueError("segment_id and start/end cannot be sent together")
        return self


class ValidateRouteSegments(BaseModel):
    segments: list[ValidateItem] = Field(max_length=200)


class ValidationIssue(BaseModel):
    severity: str
    kind: str
    message: str
    slot: int | None = None
    ref: str | None = None
    distance_m: float | None = None


class ValidationReport(BaseModel):
    is_valid: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]


# ------------------------------------------------------------------ the route

class RouteFields(BaseModel):
    name_de: str | None = None
    name_pl: str | None = None
    summary: str | None = Field(None, max_length=1000)
    summary_de: str | None = None
    summary_pl: str | None = None
    description: str | None = Field(None, max_length=10000)
    description_de: str | None = None
    description_pl: str | None = None
    sport_type_id: UUID | None = Field(None, description="Leave out: taken from the segments (the sport with the most distance).")
    difficulty_level_id: UUID | None = Field(None, description="Leave out: taken from the hardest segment.")
    difficulty_sport_id: UUID | None = Field(None, description="Leave out: taken from the hardest grade of the main sport.")


class RouteCreate(RouteFields):
    name: str = Field(min_length=1, max_length=255)
    is_public: bool = False
    plan_conditions: PlanConditionsInput | None = None


class RouteUpdate(RouteFields):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    is_public: bool | None = None
    plan_conditions: PlanConditionsInput | None = Field(None, description="Only the fields you send are changed.")

    @field_validator("name", "is_public", mode="before")
    @classmethod
    def reject_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class RouteRead(BaseModel):
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
    sport_type_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    agg_distance_m: int | None = None
    agg_elevation_gain_m: int | None = None
    agg_elevation_loss_m: int | None = None
    agg_highest_point_m: int | None = None
    agg_lowest_point_m: int | None = None
    agg_duration_s: int | None = None
    plan_condition_id: UUID | None = None
    rating_avg: float | None = None
    rating_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by: UUID


class RouteSegmentItem(BaseModel):
    # One row of the route as the route walks it (start and end swapped, ascent and descent exchanged when reversed)
    segment_id: UUID
    slot_position: int
    alt_group: int
    is_default: bool
    is_reversed: bool
    name: str | None = None
    sport_type_id: UUID
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None
    distance_m: int | None = None
    elevation_gain_m: int | None = None
    elevation_loss_m: int | None = None
    highest_elevation_m: int | None = None
    lowest_elevation_m: int | None = None
    start_point: Point | None = None
    end_point: Point | None = None
    start_poi_id: UUID | None = None
    end_poi_id: UUID | None = None
    is_public: bool
    created_by: UUID


class SportShare(BaseModel):
    sport_type_id: UUID
    distance_m: int
    segment_count: int


class DerivedClassification(BaseModel):
    sport_type_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_sport_id: UUID | None = None


class RouteDetail(RouteRead):
    sport_type: RefWithFactorDetail | None = Link()
    difficulty_level: RefRankedDetail | None = Link()
    difficulty_sport: DifficultySportDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
    plan_conditions: PlanConditionsRead | None = None
    segments: list[RouteSegmentItem] = Field(default_factory=list, description="The segment rows in slot order, the default of a slot first.")
    sport_types: list[SportShare] = Field(default_factory=list, description="The sports of the default segments, the one with the most distance first.")
    derived: DerivedClassification = Field(default_factory=DerivedClassification, description="Sport and difficulty as they would be computed from the segments now.")
    classification_differs: bool = Field(False, description="True when the stored sport or difficulty is not the derived one (for example set by hand).")


class CreatedSegmentRef(BaseModel):
    index: int = Field(description="Position of the item in the request (0 = the first element of `segments`).")
    segment_id: UUID


class RouteSaved(RouteDetail):
    warnings: list[ValidationIssue] = Field(default_factory=list, description="Gaps and mismatches that were saved because validation was 'warn'.")
    created_segments: list[CreatedSegmentRef] = Field(default_factory=list, description="The ids of the segments that this save created from inline items.")


class AlternativeLine(BaseModel):
    slot_position: int
    segment_id: UUID
    geojson: dict | None = None


class RouteGeometry(BaseModel):
    geojson: dict | None = Field(None, description="The default path: one line per segment (or a LineString), each in walking direction.")
    elevation_graph: list | None = Field(None, description="[distance_m, elevation_m] for the whole default path.")
    alternatives: list[AlternativeLine] = Field(default_factory=list)
    start_point: Point | None = None
    end_point: Point | None = None
