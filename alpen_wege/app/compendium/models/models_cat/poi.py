# Standard library
import uuid

# Third-party
from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, ContentI18nMixin, OwnedMixin, TimestampMixin


class CompendiumCatPoi(TimestampMixin, OwnedMixin, ContentI18nMixin, Base):
    __tablename__ = "compendium_cat_poi"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    altitude_m: Mapped[int | None] = mapped_column(Integer)
    data_source_url: Mapped[str | None] = mapped_column(Text)
    compendium_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_compendium_type.id"), nullable=False
    )
    poi_access_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_sub_poi_access.id")
    )
    main_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_agg_photo.id")
    )
    main_region_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compendium_cat_region.id"), nullable=False
    )
