# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, OwnedMixin, TimestampMixin


class ExplorerM2mRouteJourney(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "explorer_m2m_route_journey"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    slot_position: Mapped[int] = mapped_column(Integer, nullable=False)
    route_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_route.id", ondelete="CASCADE"), nullable=False
    )
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_agg_journey.id", ondelete="CASCADE"), nullable=False
    )
    poi_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_poi.id")
    )
    day_name: Mapped[str] = mapped_column(Text, nullable=False)
    day_summary: Mapped[str | None] = mapped_column(Text)
    day_description: Mapped[str | None] = mapped_column(Text)
