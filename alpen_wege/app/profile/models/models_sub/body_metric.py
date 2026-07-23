# Standard library
import uuid
from datetime import date

# Third-party
from sqlalchemy import Date, Real, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, CreatedOnlyMixin, UserScopedMixin


class ProfileSubBodyMetric(CreatedOnlyMixin, UserScopedMixin, Base):
    __tablename__ = "profile_sub_body_metric"
    __table_args__ = (UniqueConstraint("user_id", "recorded_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    recorded_at: Mapped[date] = mapped_column(Date, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Real, nullable=False)
