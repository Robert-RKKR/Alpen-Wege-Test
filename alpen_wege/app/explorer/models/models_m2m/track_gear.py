# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, OwnedMixin, TimestampMixin


class ExplorerM2mTrackGear(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "explorer_m2m_track_gear"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    slot_position: Mapped[int] = mapped_column(Integer, nullable=False)
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="CASCADE"), nullable=False
    )
    gear_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_gear.id", ondelete="CASCADE"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    points: Mapped[int | None] = mapped_column(Integer)
