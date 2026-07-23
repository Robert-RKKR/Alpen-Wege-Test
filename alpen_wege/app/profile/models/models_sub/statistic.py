# Standard library
import uuid

# Third-party
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin, UserScopedMixin


class ProfileSubStatistic(TimestampMixin, UserScopedMixin, Base):
    __tablename__ = "profile_sub_statistic"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "scope_year", "scope_month"),
        CheckConstraint(
            "scope IN ('all', 'year', 'month')",
            name="ck_profile_sub_statistic_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    scope_year: Mapped[int | None] = mapped_column(Integer)
    scope_month: Mapped[int | None] = mapped_column(Integer)
    total_distance_m: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    total_distance_graph = mapped_column(JSONB, nullable=True)
    total_elevation_m: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    total_elevation_graph = mapped_column(JSONB, nullable=True)
    total_activities: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_activities_graph = mapped_column(JSONB, nullable=True)
    total_time_s: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    total_time_graph = mapped_column(JSONB, nullable=True)
    total_plans_created: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_plans_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_plans_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    current_streak_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    longest_streak_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    total_points: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    unique_pois_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    unique_regions_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
