import uuid

from sqlalchemy import ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, OwnedMixin, TimestampMixin


class ExplorerM2mTrackPhoto(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "explorer_m2m_track_photo"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    slot_position: Mapped[int] = mapped_column(Integer, nullable=False)
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="CASCADE"), nullable=False
    )
    photo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("asset_agg_photo.id", ondelete="CASCADE"), nullable=False
    )
