import uuid

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, CreatedOnlyMixin


class SocialM2mFollow(CreatedOnlyMixin, Base):
    __tablename__ = "social_m2m_follow"
    __table_args__ = (
        UniqueConstraint("follower_id", "following_id"),
        CheckConstraint(
            "follower_id <> following_id",
            name="ck_social_m2m_follow_no_self",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    follower_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile_usr_user.id", ondelete="CASCADE"), nullable=False
    )
    following_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile_usr_user.id", ondelete="CASCADE"), nullable=False
    )
