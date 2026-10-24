# Standard library
import uuid

# Third-party
from sqlalchemy import CheckConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin


class MgmtRefEntityType(Base, TimestampMixin):
    __tablename__ = "mgmt_ref_entity_type"
    __table_args__ = (
        CheckConstraint(
            "tracking_mode IN ('all', 'explicit', 'none')",
            name="ck_entity_type_tracking_mode",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    module: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    tracking_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="all",
    )
    ignore_fields: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=None,
    )
