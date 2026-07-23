# Standard library
import uuid

# Third-party
from geoalchemy2 import Geometry
from sqlalchemy import ARRAY, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, ContentI18nMixin, OwnedMixin, TimestampMixin


class CompendiumCatCountry(TimestampMixin, OwnedMixin, ContentI18nMixin, Base):
    __tablename__ = "compendium_cat_country"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    iso_code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
    location = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
    )
    name_common: Mapped[str | None] = mapped_column(Text)
    name_common_de: Mapped[str | None] = mapped_column(Text)
    name_common_pl: Mapped[str | None] = mapped_column(Text)
    name_official: Mapped[str | None] = mapped_column(Text)
    name_official_de: Mapped[str | None] = mapped_column(Text)
    name_official_pl: Mapped[str | None] = mapped_column(Text)
    name_native_common = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    name_native_official = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    languages = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    currencies = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    capital: Mapped[str | None] = mapped_column(Text)
    capital_de: Mapped[str | None] = mapped_column(Text)
    capital_pl: Mapped[str | None] = mapped_column(Text)
