import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import func, update

from app.worker import model_registry  # noqa: F401
from app.compendium.cards import render, service
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.database import SyncSessionLocal
from app.management.jobs.tracked_task import TrackedTask

logger = logging.getLogger(__name__)


def _set_status(card_id: UUID, **values) -> None:
    with SyncSessionLocal() as session:
        session.execute(update(CompendiumCatCard).where(CompendiumCatCard.id == card_id).values(**values))
        session.commit()


@shared_task(
    bind=True,
    base=TrackedTask,
    name="cards.render",
    job_stage="rendering",
    acks_late=True,
    soft_time_limit=120,
    time_limit=150,
)
def render_card(self, card_id: str):
    # Renders svg, png and pdf in every language into CARD_STORAGE_DIR/{card_id}/.
    card_uuid = UUID(card_id)
    with SyncSessionLocal() as session:
        loaded = service.load_sync(session, card_uuid)
        if loaded is None:
            return {"status": "failed", "message": "The card no longer exists."}
        card, links, poi_photo = loaded
        models = {lang: service.build_render_model(card, links, lang, poi_photo) for lang in service.LANGS}

    _set_status(card_uuid, render_status="rendering")
    try:
        for lang, model in models.items():
            svg = render.render_svg(model, service.photo_data_uri(model))
            for fmt in service.STORED_FORMATS:
                service.write_atomic(service.stored_file(card_uuid, lang, fmt), render.svg_to(svg, fmt))
    except Exception:
        logger.exception("Card render failed for %s", card_id)
        _set_status(card_uuid, render_status="failed")
        return {"status": "failed", "message": "The card could not be rendered."}

    # The hash is of the data read before rendering: an edit made meanwhile leaves the files stale, never wrongly fresh.
    _set_status(
        card_uuid, render_status="done", render_version=render.TEMPLATE_VERSION,
        render_hash=render.render_hash(models["en"]), rendered_at=func.now(),
    )
    return {"status": "done", "card_id": card_id, "languages": list(models), "formats": list(service.STORED_FORMATS)}

