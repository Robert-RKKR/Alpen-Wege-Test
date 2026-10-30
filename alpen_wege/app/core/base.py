# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import Boolean, DateTime, ForeignKey, REAL, SmallInteger, Text, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
    relationship,
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
        comment=(
            "Timezone-aware UTC timestamp of when the row was first created, "
            "set automatically by the database on INSERT."
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment=(
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
        comment=(
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
            comment=(
                "UUID of the user who originally created this record. "
                "References profile_usr_user.id and is required (NOT NULL)."
            ),
        )

    @declared_attr
    def created_by_user(cls):
        # Read-only link to the creating user, loaded only when a GET asks for ?expand=created_by.
        # lazy="raise" blocks accidental loads; viewonly keeps it out of every save.
        return relationship(
            "ProfileUsrUser",
            foreign_keys=f"{cls.__name__}.created_by",
            lazy="raise",
            viewonly=True,
        )


class UserScopedMixin:
    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            ForeignKey("profile_usr_user.id", ondelete="CASCADE"),
            nullable=False,
            comment=(
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
        comment="Display name in the default language (English).",
    )
    name_de: Mapped[str | None] = mapped_column(
        Text,
        comment="German (de) translation of the display name.",
    )
    name_pl: Mapped[str | None] = mapped_column(
        Text,
        comment="Polish (pl) translation of the display name.",
    )


class SummaryL18nMixin:
    summary: Mapped[str | None] = mapped_column(
        Text,
        comment=(
            "Short summary text in the default language (English), used for "
            "previews and list views."
        ),
    )
    summary_de: Mapped[str | None] = mapped_column(
        Text,
        comment="German (de) translation of the short summary.",
    )
    summary_pl: Mapped[str | None] = mapped_column(
        Text,
        comment="Polish (pl) translation of the short summary.",
    )


class DescriptionL18nMixin:
    description: Mapped[str | None] = mapped_column(
        Text,
        comment=(
            "Long-form description in the default language (English), used "
            "for detail views and full content display."
        ),
    )
    description_de: Mapped[str | None] = mapped_column(
        Text,
        comment="German (de) translation of the long-form description.",
    )
    description_pl: Mapped[str | None] = mapped_column(
        Text,
        comment="Polish (pl) translation of the long-form description.",
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
        comment=(
            "Visibility flag indicating whether this record is publicly "
            "visible to all users. Defaults to false (private, visible only "
            "to the owner)."
        ),
    )


class ReferenceBaseMixin(TimestampMixin, CreatorMixin, NameL18nMixin):
    """Base for core_ref_* tables: timestamps + created_by + name i18n + color
    + icon_id."""

    color: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Hex color code (e.g. ) used to visually represent this reference "
            "value in the UI."
        ),
    )

    @declared_attr
    def icon_id(cls) -> Mapped[uuid.UUID]:
        # RESTRICT: an icon that is still used cannot be deleted.
        return mapped_column(
            ForeignKey("asset_agg_icon.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment=(
                "FK to asset_agg_icon with RESTRICT delete. The picture of "
                "this reference value (an SVG)."
            ),
        )


class ReferenceWithFactorMixin(ReferenceBaseMixin):
    """Extends ReferenceBaseMixin with point_factor."""

    point_factor: Mapped[float] = mapped_column(
        REAL,
        nullable=False,
        comment=(
            "Numeric multiplier applied when calculating gamification points "
            "for entities associated with this reference type."
        ),
    )


class ReferenceWithRankMixin(ReferenceWithFactorMixin):
    """Extends ReferenceWithFactorMixin with rank: the place of the value on
    the scale of its table (difficulty level, rarity, visibility, ...)."""

    rank: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment=(
            "Position of this value on the scale of its table. A higher "
            "number means harder, rarer or worse. Equal numbers are allowed "
            "(equivalent values). For difficulty_sport the scale is per "
            "sport_type_id: only grades of the same sport type can be "
            "compared. Used to find the hardest value, for example the "
            "difficulty of a route."
        ),
    )
