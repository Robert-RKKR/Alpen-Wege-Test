# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import (
    Base,
    ContentI18nMixin,
    OwnedMixin,
    PublicFlagMixin,
    TimestampMixin,
)


class ExplorerAggTrack(
    TimestampMixin, OwnedMixin, PublicFlagMixin, ContentI18nMixin, Base
):
    __tablename__ = "explorer_agg_track"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sport_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_sport_type.id")
    )
    difficulty_level_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_difficulty_level.id")
    )
    difficulty_sport_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_difficulty_sport.id")
    )
    main_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_agg_photo.id")
    )
    geo_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_sub_geo_record.id")
    )
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_sub_conditions.id")
    )
    start_poi_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_poi.id")
    )
    end_poi_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_poi.id")
    )
