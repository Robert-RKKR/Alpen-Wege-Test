import logging

from sqlalchemy.orm import selectinload

from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.routes.card.render import RenderBusy, queue_render

logger = logging.getLogger(__name__)

EAGER = [
    selectinload(CompendiumCatCard.rarity),
    selectinload(CompendiumCatCard.compendium_type),
    selectinload(CompendiumCatCard.poi),
    selectinload(CompendiumCatCard.difficulty_level),
    selectinload(CompendiumCatCard.difficulty_sport),
]


async def queue_render_quietly(db, card_id, user_id) -> None:
    # A card save never fails because of its graphic: a busy or broken queue leaves the stored files stale,
    # and GET /render draws a stale card on the fly.
    try:
        await queue_render(db, card_id, user_id)
    except RenderBusy:
        pass
    except Exception:
        logger.warning("Could not queue the render of card %s", card_id, exc_info=True)
