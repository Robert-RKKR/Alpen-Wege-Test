# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, CreatedOnlyMixin, UserScopedMixin


class ProfileM2mLikedJourney(CreatedOnlyMixin, UserScopedMixin, Base):
    __tablename__ = "profile_m2m_liked_journey"
    __table_args__ = (UniqueConstraint("user_id", "journey_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_journey.id", ondelete="CASCADE"), nullable=False
    )
