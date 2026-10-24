from sqlalchemy.orm import selectinload

from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion


EAGER = [
    selectinload(CompendiumM2mPoiRegion.poi),
    selectinload(CompendiumM2mPoiRegion.region),
]
