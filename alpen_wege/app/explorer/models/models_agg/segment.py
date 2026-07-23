# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, Real, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import (
    Base,
    ContentI18nMixin,
    OwnedMixin,
    PublicFlagMixin,
    TimestampMixin,
)


class ExplorerAggSegment(
    TimestampMixin, OwnedMixin, PublicFlagMixin, ContentI18nMixin, Base
):
    __tablename__ = "explorer_agg_segment"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    rating_avg: Mapped[float | None] = mapped_column(Real)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sport_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_sport_type.id"), nullable=False
    )
    geo_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explorer_sub_geo_record.id"), nullable=False
    )
    main_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_agg_photo.id")
    )
    start_poi_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_poi.id")
    )
    end_poi_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_poi.id")
    )
    difficulty_level_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_difficulty_level.id")
    )
    difficulty_sport_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_difficulty_sport.id")
    )
