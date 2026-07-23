# Standard library
import uuid

# Third-party
from sqlalchemy import CheckConstraint, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin, UserScopedMixin


class SocialSubRating(TimestampMixin, UserScopedMixin, Base):
    __tablename__ = "social_sub_rating"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id"),
        CheckConstraint(
            "entity_type IN ('route', 'journey', 'segment')",
            name="ck_social_sub_rating_entity_type",
        ),
        CheckConstraint(
            "score >= 1 AND score <= 5",
            name="ck_social_sub_rating_score",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
