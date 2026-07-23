# Standard library
import uuid
from datetime import datetime

# Third-party
from geoalchemy2 import Geometry
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin


class ExplorerSubWaypoint(TimestampMixin, Base):
    __tablename__ = "explorer_sub_waypoint"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    altitude_m: Mapped[int | None] = mapped_column(Integer)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[int | None] = mapped_column(Integer)
    poi_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_poi.id")
    )
