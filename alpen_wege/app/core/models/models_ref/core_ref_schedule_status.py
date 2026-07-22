import uuid

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, ReferenceWithFactorMixin


class CoreRefScheduleStatus(Base, ReferenceWithFactorMixin):
    __tablename__ = "core_ref_schedule_status"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
