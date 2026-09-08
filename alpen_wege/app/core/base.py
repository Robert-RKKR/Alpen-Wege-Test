# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import Boolean, DateTime, ForeignKey, Real, Text, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Timestamp mixins
# ---------------------------------------------------------------------------


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        description=(
            "Timezone-aware UTC timestamp of when the row was first created, "
            "set automatically by the database on INSERT."
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        description=(
            "Timezone-aware UTC timestamp of the last modification, initially "
            "set to created_at and kept current by the moddatetime trigger on "
            "every UPDATE."
        ),
    )


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        description=(
            "Timezone-aware UTC timestamp of when the row was first created, "
            "set automatically by the database on INSERT. This table does not "
            "track updates."
        ),
    )


# ---------------------------------------------------------------------------
# Ownership mixins
# ---------------------------------------------------------------------------


class CreatorMixin:
    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            ForeignKey("profile_usr_user.id"),
            nullable=False,
            description=(
                "UUID of the user who originally created this record. "
                "References profile_usr_user.id and is required (NOT NULL)."
            ),
        )


class UserScopedMixin:
    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            ForeignKey("profile_usr_user.id", ondelete="CASCADE"),
            nullable=False,
            description=(
                "UUID of the owning user. References profile_usr_user.id with "
                "ON DELETE CASCADE so all user-scoped rows are removed when "
                "the user is deleted."
            ),
        )


# ---------------------------------------------------------------------------
# Internationalization mixins
# ---------------------------------------------------------------------------


class NameL18nMixin:
    name: Mapped[str | None] = mapped_column(
        Text,
        description="Display name in the default language (English).",
    )
    name_de: Mapped[str | None] = mapped_column(
        Text,
        description="German (de) translation of the display name.",
    )
    name_pl: Mapped[str | None] = mapped_column(
        Text,
        description="Polish (pl) translation of the display name.",
    )


class SummaryL18nMixin:
    summary: Mapped[str | None] = mapped_column(
        Text,
        description=(
            "Short summary text in the default language (English), used for "
            "previews and list views."
        ),
    )
    summary_de: Mapped[str | None] = mapped_column(
        Text,
        description="German (de) translation of the short summary.",
    )
    summary_pl: Mapped[str | None] = mapped_column(
        Text,
        description="Polish (pl) translation of the short summary.",
    )


class DescriptionL18nMixin:
    description: Mapped[str | None] = mapped_column(
        Text,
        description=(
            "Long-form description in the default language (English), used "
            "for detail views and full content display."
        ),
    )
    description_de: Mapped[str | None] = mapped_column(
        Text,
        description="German (de) translation of the long-form description.",
    )
    description_pl: Mapped[str | None] = mapped_column(
        Text,
        description="Polish (pl) translation of the long-form description.",
    )


class IdentificationL18nMixin(NameL18nMixin, SummaryL18nMixin, DescriptionL18nMixin):
    pass


# ---------------------------------------------------------------------------
# Other common mixins
# ---------------------------------------------------------------------------


class PublicMixin:
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        description=(
            "Visibility flag indicating whether this record is publicly "
            "visible to all users. Defaults to false (private, visible only "
            "to the owner)."
        ),
    )


class ReferenceBaseMixin(TimestampMixin, CreatorMixin, NameL18nMixin):
    """Base for core_ref_* tables: timestamps + created_by + name i18n + color
    + icon."""

    color: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        description=(
            "Hex color code (e.g. ) used to visually represent this reference "
            "value in the UI."
        ),
    )
    icon: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        description=(
            "Icon identifier or key name used to render the visual icon for "
            "this reference value in the UI."
        ),
    )


class ReferenceWithFactorMixin(ReferenceBaseMixin):
    """Extends ReferenceBaseMixin with point_factor."""

    point_factor: Mapped[float] = mapped_column(
        Real,
        nullable=False,
        description=(
            "Numeric multiplier applied when calculating gamification points "
            "for entities associated with this reference type."
        ),
    )
