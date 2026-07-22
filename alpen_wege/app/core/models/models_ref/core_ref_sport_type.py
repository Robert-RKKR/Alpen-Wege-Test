import uuid

from sqlalchemy import CheckConstraint, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, ReferenceWithFactorMixin


class CoreRefSportType(Base, ReferenceWithFactorMixin):
    __tablename__ = "core_ref_sport_type"
    __table_args__ = (
        CheckConstraint(
            r"color ~ '^#[0-9a-fA-F]{6}$'",
            name="ck_core_ref_sport_type_color",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
