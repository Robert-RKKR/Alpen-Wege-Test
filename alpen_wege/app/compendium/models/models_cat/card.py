# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, ContentI18nMixin, OwnedMixin, TimestampMixin


class CompendiumCatCard(TimestampMixin, OwnedMixin, ContentI18nMixin, Base):
    __tablename__ = "compendium_cat_card"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str | None] = mapped_column(Text)
    rarity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_rarity.id")
    )
    compendium_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_compendium_type.id")
    )
    poi_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_poi.id")
    )
    main_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_agg_photo.id")
    )
