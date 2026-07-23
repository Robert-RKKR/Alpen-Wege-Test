# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, OwnedMixin, TimestampMixin


class ExplorerM2mTrackTrip(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "explorer_m2m_track_trip"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    slot_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="CASCADE"),
        nullable=False,
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_trip.id", ondelete="CASCADE"),
        nullable=False,
    )
    waypoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_sub_waypoint.id")
    )
    day_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    day_summary: Mapped[str | None] = mapped_column(Text)
    day_description: Mapped[str | None] = mapped_column(Text)
