import uuid

from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import (
    Base,
    ContentI18nMixin,
    OwnedMixin,
    PublicFlagMixin,
    TimestampMixin,
)


class ExplorerAggGear(
    TimestampMixin, OwnedMixin, PublicFlagMixin, ContentI18nMixin, Base
):
    __tablename__ = "explorer_agg_gear"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_company.id"), nullable=False
    )
    model: Mapped[str | None] = mapped_column(Text)
    weight_g: Mapped[int | None] = mapped_column(Integer)
    gear_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_gear_type.id"), nullable=False
    )
    main_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_agg_photo.id")
    )
