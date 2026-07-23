# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin, UserScopedMixin


class ProfileM2mUserPoi(TimestampMixin, UserScopedMixin, Base):
    __tablename__ = "profile_m2m_user_poi"
    __table_args__ = (UniqueConstraint("user_id", "poi_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    poi_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compendium_cat_poi.id", ondelete="CASCADE"), nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="SET NULL")
    )
