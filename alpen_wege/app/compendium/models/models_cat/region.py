# Standard library
import uuid

# Third-party
from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, ContentI18nMixin, OwnedMixin, TimestampMixin


class CompendiumCatRegion(TimestampMixin, OwnedMixin, ContentI18nMixin, Base):
    __tablename__ = "compendium_cat_region"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    country_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compendium_cat_country.id"), nullable=False
    )
    region_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_region_type.id"), nullable=False
    )
    iso_code: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compendium_cat_region.id")
    )
    bbox = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
