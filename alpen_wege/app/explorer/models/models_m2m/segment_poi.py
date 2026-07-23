# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, OwnedMixin, TimestampMixin


class ExplorerM2mSegmentPoi(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "explorer_m2m_segment_poi"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    slot_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    segment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_segment.id", ondelete="CASCADE"),
        nullable=False,
    )
    poi_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compendium_cat_poi.id", ondelete="CASCADE"),
        nullable=False,
    )
    distance_m: Mapped[int | None] = mapped_column(Integer)
