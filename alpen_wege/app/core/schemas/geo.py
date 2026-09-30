from typing import Annotated

from geoalchemy2.shape import to_shape
from geoalchemy2.elements import WKTElement
from pydantic import BaseModel, BeforeValidator, field_validator


class GeoPoint(BaseModel):
    type: str = "Point"
    coordinates: list[float]

    @field_validator("coordinates")
    @classmethod
    def validate_coords(cls, v):
        if len(v) != 2:
            raise ValueError("Point needs exactly [lon, lat]")
        return v


class GeoPolygon(BaseModel):
    type: str = "Polygon"
    coordinates: list[list[list[float]]]


def _parse_geo(v):
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    shape = to_shape(v)
    if shape.geom_type == "Point":
        return {"type": "Point", "coordinates": [shape.x, shape.y]}
    if shape.geom_type == "Polygon":
        return {
            "type": "Polygon",
            "coordinates": [[list(c) for c in shape.exterior.coords]],
        }
    return None


GeoPointField = Annotated[GeoPoint | None, BeforeValidator(_parse_geo)]
GeoPolygonField = Annotated[GeoPolygon | None, BeforeValidator(_parse_geo)]


def geojson_to_wkt(geo: dict | GeoPoint | GeoPolygon | None, geom_type: str = "POINT") -> WKTElement | None:
    if geo is None:
        return None
    if isinstance(geo, BaseModel):
        geo = geo.model_dump()
    if geom_type == "POINT":
        lon, lat = geo["coordinates"]
        return WKTElement(f"POINT({lon} {lat})", srid=4326)
    if geom_type == "POLYGON":
        ring = geo["coordinates"][0]
        coords = ", ".join(f"{c[0]} {c[1]}" for c in ring)
        return WKTElement(f"POLYGON(({coords}))", srid=4326)
    return None
