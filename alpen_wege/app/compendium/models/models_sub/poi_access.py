import uuid

from sqlalchemy import Boolean, Integer, Real, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class CompendiumSubPoiAccess(TimestampMixin, Base):
    __tablename__ = "compendium_sub_poi_access"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    public_transport: Mapped[bool | None] = mapped_column(Boolean)
    public_transport_info: Mapped[str | None] = mapped_column(Text)
    public_transport_info_de: Mapped[str | None] = mapped_column(Text)
    public_transport_info_pl: Mapped[str | None] = mapped_column(Text)
    parking_available: Mapped[bool | None] = mapped_column(Boolean)
    parking_capacity: Mapped[int | None] = mapped_column(Integer)
    parking_price: Mapped[float | None] = mapped_column(Real)
    parking_notes: Mapped[str | None] = mapped_column(Text)
    parking_notes_de: Mapped[str | None] = mapped_column(Text)
    parking_notes_pl: Mapped[str | None] = mapped_column(Text)
    toilet_available: Mapped[bool | None] = mapped_column(Boolean)
    water_available: Mapped[bool | None] = mapped_column(Boolean)
    access_notes: Mapped[str | None] = mapped_column(Text)
    access_notes_de: Mapped[str | None] = mapped_column(Text)
    access_notes_pl: Mapped[str | None] = mapped_column(Text)
