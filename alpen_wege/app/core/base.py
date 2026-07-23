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
    # Timezone-aware timestamp of when the row was created; set by the DB on insert.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # Timezone-aware timestamp of the last update; defaults to creation time
    # (kept current by the moddatetime trigger).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CreatedOnlyMixin:
    # Timezone-aware creation timestamp for tables that never track updates.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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
        return mapped_column(
            ForeignKey("profile_usr_user.id"),
            nullable=False,
        )


class UserScopedMixin:
    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        # Declared attribute: adds a required "user_id" FK that cascades on user delete.
        # Params:
        #   cls: the model class this mixin is applied to (provided by SQLAlchemy).
        # Returns: a mapped_column referencing profile_usr_user.id (NOT NULL, ON DELETE CASCADE).
        return mapped_column(
            ForeignKey("profile_usr_user.id", ondelete="CASCADE"),
            nullable=False,
        )


# ---------------------------------------------------------------------------
# Internationalization mixins
# ---------------------------------------------------------------------------


class NameI18nMixin:
    # Display name in the default language (English).
    name: Mapped[str | None] = mapped_column(Text)
    # German (de) translation of the name.
    name_de: Mapped[str | None] = mapped_column(Text)
    # Polish (pl) translation of the name.
    name_pl: Mapped[str | None] = mapped_column(Text)


class SummaryI18nMixin:
    # Short summary in the default language (English).
    summary: Mapped[str | None] = mapped_column(Text)
    # German (de) translation of the summary.
    summary_de: Mapped[str | None] = mapped_column(Text)
    # Polish (pl) translation of the summary.
    summary_pl: Mapped[str | None] = mapped_column(Text)


class DescriptionI18nMixin:
    # Long-form description in the default language (English).
    description: Mapped[str | None] = mapped_column(Text)
    # German (de) translation of the description.
    description_de: Mapped[str | None] = mapped_column(Text)
    # Polish (pl) translation of the description.
    description_pl: Mapped[str | None] = mapped_column(Text)


class ContentI18nMixin(NameI18nMixin, SummaryI18nMixin, DescriptionI18nMixin):
    pass


# ---------------------------------------------------------------------------
# Other common mixins
# ---------------------------------------------------------------------------


class PublicFlagMixin:
    # Visibility flag: True if the row is publicly visible; defaults to private (False).
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )


class ReferenceBaseMixin(TimestampMixin, OwnedMixin, NameI18nMixin):
    """Base for core_ref_* tables: timestamps + created_by + name i18n + color + icon."""

    # Hex color (e.g. "#1a2b3c") used to render this reference value in the UI.
    color: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    # Icon identifier (name/key) used to render this reference value in the UI.
    icon: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class ReferenceWithFactorMixin(ReferenceBaseMixin):
    """Extends ReferenceBaseMixin with point_factor."""

    # Multiplier applied when awarding points for entities of this reference type.
    point_factor: Mapped[float] = mapped_column(
        Real,
        nullable=False,
    )
