import uuid

from sqlalchemy import ForeignKey, Integer, Real, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import (
    Base,
    ContentI18nMixin,
    OwnedMixin,
    PublicFlagMixin,
    TimestampMixin,
)


class ExplorerAggJourney(
    TimestampMixin, OwnedMixin, PublicFlagMixin, ContentI18nMixin, Base
):
    __tablename__ = "explorer_agg_journey"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    rating_avg: Mapped[float | None] = mapped_column(Real)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    length_days: Mapped[int | None] = mapped_column(Integer)
    agg_distance_m: Mapped[int | None] = mapped_column(Integer)
    agg_elevation_gain_m: Mapped[int | None] = mapped_column(Integer)
    agg_elevation_loss_m: Mapped[int | None] = mapped_column(Integer)
    agg_highest_point_m: Mapped[int | None] = mapped_column(Integer)
    agg_lowest_point_m: Mapped[int | None] = mapped_column(Integer)
    agg_duration_s: Mapped[int | None] = mapped_column(Integer)
    difficulty_level_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_difficulty_level.id")
    )
    difficulty_sport_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_difficulty_sport.id")
    )
    sport_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_sport_type.id")
    )
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_sub_plan_conditions.id")
    )
