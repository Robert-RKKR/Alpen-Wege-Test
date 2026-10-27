# Standard library
import uuid

# Third-party
from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Local application
from app.core.base import Base


class MgmtLogEvent(Base):
    __tablename__ = "mgmt_log_event"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    seq: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        nullable=False,
        unique=True,
    )
    entity_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mgmt_ref_entity_type.id"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    changed_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile_usr_user.id"),
        nullable=False,
    )
    changed_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,  # ix_mgmt_log_event_changed_at, used by the retention job
    )
    request_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    entity_type = relationship("MgmtRefEntityType", lazy="joined")
    changed_by_user = relationship("ProfileUsrUser", foreign_keys=[changed_by], lazy="raise", viewonly=True)
