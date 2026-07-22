import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin, UserScopedMixin


class SocialSubComment(TimestampMixin, UserScopedMixin, Base):
    __tablename__ = "social_sub_comment"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('route', 'journey', 'segment', 'track', 'trip', 'post')",
            name="ck_social_sub_comment_entity_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("social_sub_comment.id", ondelete="CASCADE")
    )
