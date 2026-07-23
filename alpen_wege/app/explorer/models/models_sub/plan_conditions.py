# Standard library
import uuid

# Third-party
from sqlalchemy import ARRAY, Boolean, Integer, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin


class ExplorerSubPlanConditions(TimestampMixin, Base):
    __tablename__ = "explorer_sub_plan_conditions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    equipment_required: Mapped[dict | None] = mapped_column(JSON)
    equipment_optional: Mapped[dict | None] = mapped_column(JSON)
    permit_required: Mapped[bool | None] = mapped_column(Boolean)
    permit_info: Mapped[str | None] = mapped_column(Text)
    permit_info_de: Mapped[str | None] = mapped_column(Text)
    permit_info_pl: Mapped[str | None] = mapped_column(Text)
    guide_recommended: Mapped[bool | None] = mapped_column(Boolean)
    min_age: Mapped[int | None] = mapped_column(Integer)
    max_group_size: Mapped[int | None] = mapped_column(Integer)
    best_months = mapped_column(ARRAY(Integer), nullable=True)
    best_months_note: Mapped[str | None] = mapped_column(Text)
    best_months_note_de: Mapped[str | None] = mapped_column(Text)
    best_months_note_pl: Mapped[str | None] = mapped_column(Text)
