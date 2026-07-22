import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, OwnedMixin, TimestampMixin


class ExplorerM2mSegmentRoute(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "explorer_m2m_segment_route"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_segment.id", ondelete="CASCADE"), nullable=False
    )
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_route.id", ondelete="CASCADE"), nullable=False
    )
    slot_position: Mapped[int] = mapped_column(Integer, nullable=False)
    alt_group: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_reversed: Mapped[bool] = mapped_column(Boolean, nullable=False)
