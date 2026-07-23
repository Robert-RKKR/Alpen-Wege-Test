# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, OwnedMixin, TimestampMixin


class CompendiumM2mPoiRegion(TimestampMixin, OwnedMixin, Base):
    __tablename__ = "compendium_m2m_poi_region"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    poi_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compendium_cat_poi.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compendium_cat_region.id", ondelete="CASCADE"),
        nullable=False,
    )
    slot_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
