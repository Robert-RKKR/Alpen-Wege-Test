import uuid

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Integer, JSON, Real, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class ExplorerSubGeoRecord(TimestampMixin, Base):
    __tablename__ = "explorer_sub_geo_record"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    gpx_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("asset_agg_gpx.id")
    )
    geo_performance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("explorer_sub_geo_performance.id")
    )
    geojson: Mapped[dict | None] = mapped_column(JSON)
    elevation_graph: Mapped[dict | None] = mapped_column(JSON)
    track_types: Mapped[dict | None] = mapped_column(JSON)
    elevation: Mapped[int | None] = mapped_column(Integer)
    total_points: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[int | None] = mapped_column(Integer)
    elevation_gain_m: Mapped[int | None] = mapped_column(Integer)
    elevation_loss_m: Mapped[int | None] = mapped_column(Integer)
    highest_elevation_m: Mapped[int | None] = mapped_column(Integer)
    lowest_elevation_m: Mapped[int | None] = mapped_column(Integer)
    avg_grade: Mapped[float | None] = mapped_column(Real)
    highest_grade: Mapped[float | None] = mapped_column(Real)
    start_location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    end_location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
