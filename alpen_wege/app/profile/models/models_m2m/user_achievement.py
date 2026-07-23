# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin, UserScopedMixin


class ProfileM2mUserAchievement(TimestampMixin, UserScopedMixin, Base):
    __tablename__ = "profile_m2m_user_achievement"
    __table_args__ = (
        Index(
            "ix_profile_m2m_user_achievement_unique_first",
            "user_id",
            "achievement_id",
            unique=True,
            postgresql_where=text("NOT is_repeat"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile_cat_achievement.id"), nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)
    is_repeat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="SET NULL")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_trip.id", ondelete="SET NULL")
    )
