from typing import Literal
from uuid import UUID

from fastapi import Depends, Query, Response, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.compendium.cards import service
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.core.dependencies import get_db
from app.core.utils.api_paths import job_url
from app.core.utils.responses import ApiResponse, AppError, ok
from app.explorer.services.dispatch import enqueue_render_card
from app.management.jobs.events import publish_job_event_async
from app.management.jobs.kinds import TASK_NAME, JobKind
from app.management.jobs.service import create_job, fail_job
from app.management.schemas.job import JobAccepted
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router

_DESCRIPTION = (
    "The card as printed. `format=json` gives the render model (every value on the card, translated); "
    "`svg`, `png` (300 dpi), `jpg` (300 dpi) and `pdf` give the file, 63x88 mm with 3 mm bleed. "
    "Files made by the render job are served when they are up to date, otherwise the card is drawn now. "
    "`download=true` asks the browser to save the file."
)


@router.get(
    "/{card_id}/render",
    summary="Card graphic (JSON, SVG, PNG, JPG or PDF)",
    description=_DESCRIPTION,
    responses={200: {"content": {mime: {} for mime in service.FORMATS.values()}}},
)
async def get_card_render(
    card_id: UUID,
    format: Literal["json", "svg", "png", "jpg", "pdf"] = Query("svg"),
    lang: Literal["en", "de", "pl"] = Query("en"),
    download: bool = Query(False),
    access: AccessContext = Depends(resource_access("card", "read")),
    db: AsyncSession = Depends(get_db),
):
    loaded = await service.load_async(db, card_id)
    check_object_access(access, loaded[0] if loaded else None, not_found_msg="Card not found")
    card, links, poi_photo = loaded
    model = service.build_render_model(card, links, lang, poi_photo)
    if format == "json":
        return ok(model)

    stored_fmt = "png" if format == "jpg" else format
    stored = service.stored_file(card.id, lang, stored_fmt)
    fresh = stored.is_file() and service.is_fresh(card, service.build_render_model(card, links, "en", poi_photo))
    if fresh and format != "jpg":
        data = await run_in_threadpool(stored.read_bytes)
    else:
        data = await run_in_threadpool(service.render_card, model, format)

    filename = f"card-{card.card_number:03d}-{lang}.{format}"
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type=service.FORMATS[format],
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
            "X-Content-Type-Options": "nosniff",
            # an SVG opened directly must not run anything, even if a value ever slipped past escaping
            "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'",
        },
    )


class RenderBusy(Exception):
    pass


async def queue_render(db: AsyncSession, card_id: UUID, user_id: UUID) -> dict:
    # Queue the render job of a card; the caller has committed the card. RenderBusy when a render is already
    # queued (it reads the card when it starts, so it picks up this change too); AppError 503 when queueing failed.
    try:
        job = await create_job(
            db, user_id=user_id, kind=JobKind.CARD_RENDER, task_name=TASK_NAME[JobKind.CARD_RENDER],
            subject_type="card", subject_id=card_id,
        )
        await db.execute(update(CompendiumCatCard).where(CompendiumCatCard.id == card_id).values(render_status="pending"))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise RenderBusy
    await publish_job_event_async(job)
    try:
        await run_in_threadpool(enqueue_render_card, card_id, job["id"])
    except Exception:
        failed = await fail_job(db, job["id"], "The render could not be queued.")
        await db.commit()
        if failed is not None:
            await publish_job_event_async(failed)
        raise AppError(503, "Failed to queue the render.")
    return job


@router.post(
    "/{card_id}/render",
    response_model=ApiResponse[JobAccepted],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Render the card files again",
    description="Starts a job that writes SVG, PNG and PDF in English, German and Polish. `409` when one is already queued or running.",
)
async def post_card_render(
    card_id: UUID,
    response: Response,
    access: AccessContext = Depends(resource_access("card", "update")),
    db: AsyncSession = Depends(get_db),
):
    loaded = await service.load_async(db, card_id)
    check_object_access(access, loaded[0] if loaded else None, not_found_msg="Card not found")
    try:
        job = await queue_render(db, card_id, access.user.id)
    except RenderBusy:
        raise AppError(409, "A render of this card is already queued or running.")
    response.headers["Location"] = job_url(job["id"])
    return ok(JobAccepted(job_id=job["id"]), code=202, message="Render queued")

