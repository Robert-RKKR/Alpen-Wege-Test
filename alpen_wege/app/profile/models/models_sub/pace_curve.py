# Standard library
import uuid

# Third-party
from sqlalchemy import ForeignKey, Integer, Real, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin, UserScopedMixin


class ProfileSubPaceCurve(TimestampMixin, UserScopedMixin, Base):
    __tablename__ = "profile_sub_pace_curve"
    __table_args__ = (UniqueConstraint("user_id", "sport_type_id", "gradient_bin"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    sport_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core_ref_sport_type.id"),
        nullable=False,
    )
    gradient_bin: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    speed_kmh: Mapped[float] = mapped_column(
        Real,
        nullable=False,
    )
    sample_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
