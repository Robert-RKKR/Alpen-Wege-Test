# Standard library
import uuid

# Third-party
from sqlalchemy import Text, func
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


class AssetAggGpx(
    TimestampMixin, OwnedMixin, PublicFlagMixin, NameI18nMixin, SummaryI18nMixin, Base
):
    __tablename__ = "asset_agg_gpx"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )
