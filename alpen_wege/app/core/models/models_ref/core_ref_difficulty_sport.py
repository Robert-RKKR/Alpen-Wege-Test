import uuid

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, ReferenceWithFactorMixin


class CoreRefDifficultySport(Base, ReferenceWithFactorMixin):
    __tablename__ = "core_ref_difficulty_sport"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    sport_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core_ref_sport_type.id")
    )
