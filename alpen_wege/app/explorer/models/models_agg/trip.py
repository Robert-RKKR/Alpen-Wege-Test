# Standard library
import uuid
from datetime import date

# Third-party
from sqlalchemy import Date, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import (
    Base,
    ContentI18nMixin,
    OwnedMixin,
    PublicFlagMixin,
    TimestampMixin,
)


class ExplorerAggTrip(
    TimestampMixin, OwnedMixin, PublicFlagMixin, ContentI18nMixin, Base
):
    __tablename__ = "explorer_agg_trip"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    length_days: Mapped[int | None] = mapped_column(Integer)
    first_day: Mapped[date | None] = mapped_column(Date)
    last_day: Mapped[date | None] = mapped_column(Date)
    sport_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_sport_type.id")
    )
