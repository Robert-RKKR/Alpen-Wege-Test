from sqlalchemy.orm import selectinload

from app.compendium.models.models_cat.post import CompendiumCatPost


EAGER = [
    selectinload(CompendiumCatPost.post_type),
]
