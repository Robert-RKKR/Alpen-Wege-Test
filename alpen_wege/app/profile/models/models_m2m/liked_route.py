import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, CreatedOnlyMixin, UserScopedMixin


class ProfileM2mLikedRoute(CreatedOnlyMixin, UserScopedMixin, Base):
    __tablename__ = "profile_m2m_liked_route"
    __table_args__ = (
        UniqueConstraint("user_id", "route_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_route.id", ondelete="CASCADE"), nullable=False
    )
