# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Local application
from app.core.base import Base, TimestampMixin


class AuthUserCredentials(TimestampMixin, Base):
    __tablename__ = "auth_user_credentials"
    __table_args__ = (
        CheckConstraint(
            "user_group IN ('admin', 'editor', 'user')",
            name="ck_auth_user_credentials_user_group",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile_usr_user.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    user_group: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="user",
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("ProfileUsrUser", back_populates="credentials")
