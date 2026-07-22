import uuid

from sqlalchemy import ForeignKey, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class ExplorerSubConditions(TimestampMixin, Base):
    __tablename__ = "explorer_sub_conditions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    temperature_avg: Mapped[int | None] = mapped_column(Integer)
    temperature_min: Mapped[int | None] = mapped_column(Integer)
    temperature_max: Mapped[int | None] = mapped_column(Integer)
    equipment_used: Mapped[dict | None] = mapped_column(JSON)
    visibility_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_visibility.id")
    )
    snow_condition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_snow_condition.id")
    )
    trail_condition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_trail_condition.id")
    )
    weather_condition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_weather_condition.id")
    )
