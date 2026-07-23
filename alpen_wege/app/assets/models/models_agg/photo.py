# Standard library
import uuid
from datetime import datetime

# Third-party
from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import (
    Base,
    NameI18nMixin,
    OwnedMixin,
    PublicFlagMixin,
    SummaryI18nMixin,
    TimestampMixin,
)


class AssetAggPhoto(
    TimestampMixin, OwnedMixin, PublicFlagMixin, NameI18nMixin, SummaryI18nMixin, Base
):
    __tablename__ = "asset_agg_photo"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    altitude_m: Mapped[int | None] = mapped_column(Integer)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
