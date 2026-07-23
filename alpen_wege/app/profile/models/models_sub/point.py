# Standard library
import uuid
from datetime import date

# Third-party
from sqlalchemy import Date, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, CreatedOnlyMixin, UserScopedMixin


class ProfileSubPoint(CreatedOnlyMixin, UserScopedMixin, Base):
    __tablename__ = "profile_sub_point"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    received_at: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    reason_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_point_reason.id"),
        nullable=False,
    )
    user_achievement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profile_m2m_user_achievement.id", ondelete="SET NULL")
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="SET NULL")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_trip.id", ondelete="SET NULL")
    )
