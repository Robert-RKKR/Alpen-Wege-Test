import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin, UserScopedMixin


class ProfileSubSchedule(TimestampMixin, UserScopedMixin, Base):
    __tablename__ = "profile_sub_schedule"
    __table_args__ = (
        CheckConstraint(
            "route_id IS NOT NULL OR journey_id IS NOT NULL",
            name="ck_profile_sub_schedule_entity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_route.id", ondelete="SET NULL")
    )
    journey_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_journey.id", ondelete="SET NULL")
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="SET NULL")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_trip.id", ondelete="SET NULL")
    )
    planned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_schedule_status.id"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
