from typing import Literal
from uuid import UUID

from fastapi import Depends, Query, Request, Response, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.compendium.cards import render as card_render
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

RENDER_PARAMS = {"format", "lang", "ratio", "style", "dpi", "download"}

_DESCRIPTION = (
    "The card as printed. `format=json` gives the render model (every value on the card, translated); "
    "`lang` picks the language of every text on the card (name, description, country, region, type, rarity, "
    "difficulty, labels). A text that is empty in that language is taken from the next language that has one "
    "(en, de, pl in this order), first from the card, then from the POI. "
    "`ratio` is the shape of the card as width:height (default 63:88, the trading card; also 1:1, 4:5, 9:16, 3:2, "
    "16:9, ...), whole numbers 1 to 100, between 2:5 and 5:2. From 13:10 on the photo moves to the left of the texts. "
    "The shorter side is always 63 mm, so text keeps its size. "
    "`style` is the look of the card: `standard` (default) or `3d` (raised frame, glass panels, holographic sheen); "
    "any other name answers 422. "
    "`dpi` is the sharpness of a `png` or `jpg`, 72 to 2000 (default 300: 815 x 1110 px on 63:88; `dpi=600` is twice as "
    "wide and high). The file records it, so a print program knows the size. A wide or tall shape has more pixels at the "
    "same dpi, so very high values answer 422 with the highest dpi that fits. It is ignored for `svg`, `pdf` and `json`. "
    "Only 63:88 in the standard style at 300 dpi is stored by the render job; other ratios, styles and dpi are drawn on request. "
    "Any other parameter answers 422. "
    "`svg`, `png` (300 dpi), `jpg` (300 dpi) and `pdf` give the file with 3 mm bleed in the rarity colour. "
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
    request: Request,
    card_id: UUID,
    format: Literal["json", "svg", "png", "jpg", "pdf"] = Query("svg", description="What to return: json (the render model, every value on the card), svg, png, jpg or pdf (print, with 3 mm bleed). Default svg."),
    lang: Literal["en", "de", "pl"] = Query("en", description="Language of every text on the card: en, de or pl. A text empty in that language is taken from the next language that has one (en, de, pl)."),
    ratio: str = Query("63:88", max_length=7, description="Shape as width:height, whole numbers 1 to 100, between 2:5 and 5:2. Default 63:88 (trading card); also 1:1, 4:5, 9:16, 3:2, 16:9. The shorter side is always 63 mm; from 13:10 on the photo moves to the left of the texts."),
    style: str = Query(card_render.DEFAULT_STYLE, max_length=20, description="Look of the card: standard (default, flat) or 3d (raised frame, glass panels, holographic sheen). Any other name answers 422."),
    dpi: int | None = Query(None, ge=card_render.MIN_DPI, le=card_render.MAX_DPI, description=f"Sharpness of a png or jpg: pixels per inch of the printed card, {card_render.MIN_DPI} to {card_render.MAX_DPI}, default {card_render.DEFAULT_DPI} (815 x 1110 px on 63:88; 600 gives twice the width and height). The jpg records it. Very wide or tall shapes allow less (16:9 up to 1990, 5:2 up to 1690): a higher value answers 422 and names the limit. Ignored for svg, pdf and json."),
    download: bool = Query(False, description="true: the browser or Postman saves the file (Content-Disposition attachment); false (default): it is shown. The file content is the same."),
    access: AccessContext = Depends(resource_access("card", "read")),
    db: AsyncSession = Depends(get_db),
):
    unknown = sorted(set(request.query_params) - RENDER_PARAMS)
    if unknown:
        # card_lang / card_ratio are Postman variables, not parameters: say so instead of drawing the default card
        text = f"Unknown parameter(s): {', '.join(unknown)}. Allowed: format, lang, ratio, style, dpi, download."
        raise AppError(422, "Validation failed", error_message=text,
                       error_errors=[{"field": f"query.{name}", "code": "unknown_parameter", "message": text} for name in unknown])
    try:
        size = card_render.parse_ratio(ratio)
    except ValueError as exc:
        raise AppError(422, "Validation failed", error_message=str(exc),
                       error_errors=[{"field": "query.ratio", "code": "ratio", "message": str(exc)}])
    try:
        style = card_render.parse_style(style)
    except ValueError as exc:
        raise AppError(422, "Validation failed", error_message=str(exc),
                       error_errors=[{"field": "query.style", "code": "style", "message": str(exc)}])
    loaded = await service.load_async(db, card_id)
    check_object_access(access, loaded[0] if loaded else None, not_found_msg="Card not found")
    card, links, poi_photo, flag_icons = loaded
    models = {code: service.build_render_model(card, links, code, poi_photo, flag_icons) for code in service.LANGS}
    model = models[lang]
    if format == "json":
        return ok(model)

    stored = service.stored_file(card.id, lang, format)
    # dpi only changes a png / jpg; svg, pdf and json are vector or text
    sharpness = dpi if format in ("png", "jpg") and dpi else card_render.DEFAULT_DPI
    try:
        card_render.check_dpi(size, sharpness)
    except ValueError as exc:
        raise AppError(422, "Validation failed", error_message=str(exc),
                       error_errors=[{"field": "query.dpi", "code": "dpi", "message": str(exc)}])
    # the render job stores only the default shape in the default style at the default dpi
    fresh = (size == card_render.DEFAULT_RATIO and style == card_render.DEFAULT_STYLE
             and sharpness == card_render.DEFAULT_DPI and stored.is_file() and service.is_fresh(card, models))
    if fresh:
        data = await run_in_threadpool(stored.read_bytes)
    else:
        data = await run_in_threadpool(service.render_card, model, format, size, style, sharpness, service.flag_svgs(flag_icons))

    shape = "" if size == card_render.DEFAULT_RATIO else f"-{size[0]}x{size[1]}"
    look = "" if style == card_render.DEFAULT_STYLE else f"-{style}"
    sharp = "" if sharpness == card_render.DEFAULT_DPI else f"-{sharpness}dpi"
    filename = f"card-{card.card_number:0{card_render.NUMBER_DIGITS}d}-{lang}{shape}{look}{sharp}.{format}"
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
    description="Starts a job that writes SVG, PNG, JPG and PDF (63:88) in English, German and Polish. `409` when one is already queued or running.",
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

