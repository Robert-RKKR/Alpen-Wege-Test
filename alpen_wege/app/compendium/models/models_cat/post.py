# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, ContentI18nMixin, OwnedMixin, TimestampMixin


class CompendiumCatPost(TimestampMixin, OwnedMixin, ContentI18nMixin, Base):
    __tablename__ = "compendium_cat_post"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    main_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_agg_photo.id")
    )
    post_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_post_type.id"), nullable=False
    )
