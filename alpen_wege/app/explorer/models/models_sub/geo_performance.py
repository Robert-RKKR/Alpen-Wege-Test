# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import DateTime, Integer, JSON, Real, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin


class ExplorerSubGeoPerformance(TimestampMixin, Base):
    __tablename__ = "explorer_sub_geo_performance"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_time_s: Mapped[int | None] = mapped_column(Integer)
    moving_time_s: Mapped[int | None] = mapped_column(Integer)
    stop_time_s: Mapped[int | None] = mapped_column(Integer)
    moving_ratio: Mapped[float | None] = mapped_column(Real)
    avg_speed_kmh: Mapped[float | None] = mapped_column(Real)
    moving_avg_speed_kmh: Mapped[float | None] = mapped_column(Real)
    ascent_avg_speed_kmh: Mapped[float | None] = mapped_column(Real)
    descent_avg_speed_kmh: Mapped[float | None] = mapped_column(Real)
    max_speed_kmh: Mapped[float | None] = mapped_column(Real)
    max_ascent_speed_kmh: Mapped[float | None] = mapped_column(Real)
    max_descent_speed_kmh: Mapped[float | None] = mapped_column(Real)
    avg_heart_rate: Mapped[int | None] = mapped_column(Integer)
    max_heart_rate: Mapped[int | None] = mapped_column(Integer)
    min_heart_rate: Mapped[int | None] = mapped_column(Integer)
    calories_burned: Mapped[int | None] = mapped_column(Integer)
    steps_count: Mapped[int | None] = mapped_column(Integer)
    heart_graph: Mapped[dict | None] = mapped_column(JSON)
    speed_pattern: Mapped[dict | None] = mapped_column(JSON)
