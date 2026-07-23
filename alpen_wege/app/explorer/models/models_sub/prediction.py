# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, OwnedMixin, TimestampMixin


class ExplorerSubPrediction(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "explorer_sub_prediction"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_route.id", ondelete="CASCADE"), nullable=False
    )
    predicted_s: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_moving_s: Mapped[int | None] = mapped_column(Integer)
    model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    inputs: Mapped[dict | None] = mapped_column(JSON)
    track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_agg_track.id", ondelete="SET NULL")
    )
