# Standard library
import uuid

# Third-party
from sqlalchemy import Boolean, ForeignKey, Real, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, ContentI18nMixin, OwnedMixin, TimestampMixin


class ProfileCatAchievement(TimestampMixin, OwnedMixin, ContentI18nMixin, Base):
    __tablename__ = "profile_cat_achievement"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    point_factor: Mapped[float] = mapped_column(Real, nullable=False)
    criteria = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    is_repeatable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    rarity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_rarity.id"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_achievement_category.id"), nullable=False
    )
    criteria_scope_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_achievement_scope.id"), nullable=False
    )
    criteria_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_achievement_type.id"), nullable=False
    )
