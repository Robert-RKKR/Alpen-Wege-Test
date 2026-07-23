# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import Boolean, DateTime, ForeignKey, Real, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Timestamp mixins
# ---------------------------------------------------------------------------


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreatedOnlyMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Ownership mixins
# ---------------------------------------------------------------------------


class OwnedMixin:
    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID]:
        # Declared attribute: adds a required "created_by" FK to the owning user.
        # Params:
        #   cls: the model class this mixin is applied to (provided by SQLAlchemy).
        # Returns: a mapped_column referencing profile_usr_user.id (NOT NULL).
        return mapped_column(ForeignKey("profile_usr_user.id"), nullable=False)


class UserScopedMixin:
    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        # Declared attribute: adds a required "user_id" FK that cascades on user delete.
        # Params:
        #   cls: the model class this mixin is applied to (provided by SQLAlchemy).
        # Returns: a mapped_column referencing profile_usr_user.id (NOT NULL, ON DELETE CASCADE).
        return mapped_column(
            ForeignKey("profile_usr_user.id", ondelete="CASCADE"), nullable=False
        )


# ---------------------------------------------------------------------------
# Internationalization mixins
# ---------------------------------------------------------------------------


class NameI18nMixin:
    name: Mapped[str | None] = mapped_column(Text)
    name_de: Mapped[str | None] = mapped_column(Text)
    name_pl: Mapped[str | None] = mapped_column(Text)


class SummaryI18nMixin:
    summary: Mapped[str | None] = mapped_column(Text)
    summary_de: Mapped[str | None] = mapped_column(Text)
    summary_pl: Mapped[str | None] = mapped_column(Text)


class DescriptionI18nMixin:
    description: Mapped[str | None] = mapped_column(Text)
    description_de: Mapped[str | None] = mapped_column(Text)
    description_pl: Mapped[str | None] = mapped_column(Text)


class ContentI18nMixin(NameI18nMixin, SummaryI18nMixin, DescriptionI18nMixin):
    pass


# ---------------------------------------------------------------------------
# Other common mixins
# ---------------------------------------------------------------------------


class PublicFlagMixin:
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )


class ReferenceBaseMixin(TimestampMixin, OwnedMixin, NameI18nMixin):
    """Base for core_ref_* tables: timestamps + created_by + name i18n + color + icon."""

    color: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(Text, nullable=False)


class ReferenceWithFactorMixin(ReferenceBaseMixin):
    """Extends ReferenceBaseMixin with point_factor."""

    point_factor: Mapped[float] = mapped_column(Real, nullable=False)
