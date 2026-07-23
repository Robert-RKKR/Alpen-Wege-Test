# Standard library
import uuid

# Third-party
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, ReferenceWithFactorMixin


class CoreRefTrailCondition(Base, ReferenceWithFactorMixin):
    __tablename__ = "core_ref_trail_condition"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
