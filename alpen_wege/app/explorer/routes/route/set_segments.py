# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.config import get_settings
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.utils.event_logger import log_created, log_updated
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.models.models_m2m.segment_route import ExplorerM2mSegmentRoute as Link
from app.explorer.schemas.route import RouteSaved, SetRouteSegments
from app.explorer.services import aggregate, segment_build
from app.explorer.services.continuity import SlotItem, check_structure, validate
from app.explorer.services.route_rules import publish_own_segments
from app.explorer.services.route_view import apply_state, segment_facts, slot_item
from app.explorer.services.segment_http import build
from app.explorer.services.segment_persist import add_segment, ensure_refs, segment_fields
from app.explorer.services.track_source import clip_source_path
from app.explorer.services.visibility import scope_of, visible

from ._router import router
from ._shared import detail, invalid_route

settings = get_settings()


def _forbidden(text: str) -> AppError:
    return AppError(403, "Access denied", error_message=text)


def _changed_meanwhile() -> AppError:
    return AppError(409, "Conflict", error_message="A segment or the route was changed or deleted at the same time. Load the route again and repeat the save.")


@router.put("/{route_id}/segments", response_model=ApiResponse[RouteSaved])
async def set_route_segments(
    route_id: UUID,
    body: SetRouteSegments,
    access: AccessContext = Depends(resource_access("route", "update")),
    db: AsyncSession = Depends(get_db),
):
    # Replaces the whole segment list of the route in one transaction. Items are existing segments (segment_id) or new
    # ones that are created right here (inline: drawn points or a part of one of your tracks). Then the segments are
    # checked (slots, alternatives, gaps), the totals are recomputed and empty sport/difficulty fields are filled.
    # Any failure leaves nothing behind, not even the new segments.
    user = access.user
    route = await db.get(ExplorerAggRoute, route_id)
    check_object_access(access, route, not_found_msg="Route not found")
    await db.refresh(route, with_for_update=True)       # after the access check: nobody else saves, publishes or deletes this route meanwhile
    items = body.segments

    # 1. the shape of the list, before any work is done
    shape = [
        SlotItem(f"item {i}", it.slot_position, it.is_default, it.is_reversed, None, None, it.alt_group, it.segment_id)
        for i, it in enumerate(items)
    ]
    problems = check_structure(shape, settings.ROUTE_MAX_SEGMENTS)
    if problems:
        raise invalid_route(problems)
    inline = [(i, it.inline) for i, it in enumerate(items) if it.inline is not None]
    drawn = sum(len(x.coordinates) for _, x in inline if x.coordinates)
    if drawn > settings.ROUTE_SAVE_MAX_POINTS:
        raise AppError(422, f"One save can have at most {settings.ROUTE_SAVE_MAX_POINTS} drawn points in all its new segments.")

    # 2. the existing segments: they must exist and be visible to the caller (anything else is a 404), and the owner of
    #    the route must be able to see them too (his own or public ones): an administrator cannot hand a private segment
    #    of his own to the route of somebody else. The segments are locked until the end of the save.
    existing_ids = [it.segment_id for it in items if it.segment_id is not None]
    facts = {}
    if existing_ids:
        read_scope = await scope_of(db, user, "segment", "read")
        if read_scope is None:
            raise _forbidden("Your role may not read segments.")
        facts = await segment_facts(db, existing_ids, lock=True)
        missing = [str(i) for i in set(existing_ids) if i not in facts or not visible(read_scope, user.id, facts[i].segment.created_by, facts[i].segment.is_public)]
        if missing:
            raise AppError(404, "Not found", error_message="Segment not found or not visible to you: " + ", ".join(sorted(missing)))
        private = [str(i) for i in set(existing_ids) if not (facts[i].segment.is_public or facts[i].segment.created_by == route.created_by)]
        if private:
            text = "The owner of the route cannot see these segments (private to somebody else): " + ", ".join(sorted(private)) + "."
            raise AppError(422, "Validation failed", error_message=text, error_errors=[{"field": "segments", "code": "segment_not_usable", "message": text}])

    # 3. the new segments
    created: dict[int, UUID] = {}
    if inline:
        if await scope_of(db, user, "segment", "create") is None:
            raise _forbidden("Your role may not create segments.")
        tracks = {}      # a track that several items cut from is read once
        for index, spec in inline:
            if spec.coordinates is not None:
                processed = await build(segment_build.from_coordinates, spec.coordinates)
            else:
                path = await clip_source_path(db, user, spec.track_id)
                if path not in tracks:
                    tracks[path] = await build(segment_build.load_track, path)
                processed = await build(segment_build.from_cleaned_clip, tracks[path], spec.start_distance_m, spec.end_distance_m)
            fields = segment_fields(spec)
            fields["is_public"] = True if route.is_public else bool(spec.is_public)   # a public route shows only public segments
            await ensure_refs(db, fields)
            segment = await add_segment(db, processed, user_id=user.id, fields=fields)
            log_created(db, segment, user.id)
            created[index] = segment.id
        facts.update(await segment_facts(db, list(created.values())))

    # 4. the new rows
    links = [
        Link(
            route_id=route.id, segment_id=it.segment_id if it.segment_id is not None else created[i],
            slot_position=it.slot_position, alt_group=it.slot_position, is_default=it.is_default,
            is_reversed=it.is_reversed, created_by=user.id,
        )
        for i, it in enumerate(items)
    ]

    # 5. the check: errors always stop the save; warnings (gaps, alternatives that do not fit) stop it when strict
    result = validate([slot_item(l, facts[l.segment_id]) for l in links], settings.CONTINUITY_THRESHOLD_M, settings.ROUTE_MAX_SEGMENTS)
    stopping = result.errors + (result.warnings if body.validation == "strict" else [])
    if stopping:
        raise invalid_route(stopping)

    # 6. save: publish rule, replace the rows, totals and classification. A database conflict here (a segment that was
    #    deleted meanwhile) is a 409, not a 500.
    user_id = user.id
    try:
        if route.is_public:
            for segment in publish_own_segments(route, facts):
                log_updated(db, segment, {"is_public": False}, {"is_public": True}, user_id)
        watched = (*aggregate.AGG_FIELDS, *aggregate.CLASSIFICATION_FIELDS)
        before = {name: getattr(route, name) for name in watched}
        await db.execute(delete(Link).where(Link.route_id == route.id))
        db.add_all(links)
        await db.flush()
        apply_state(route, links, facts)
        route.updated_at = func.now()
        after = {name: getattr(route, name) for name in watched}
        log_updated(db, route, before, {k: v for k, v in after.items() if v != before[k]}, user_id)
        await db.flush()
        await db.refresh(route)
        data = await detail(
            db, route, user, links=links, facts=facts,
            warnings=[i.as_dict() for i in result.warnings],
            created_segments=[{"index": i, "segment_id": s} for i, s in sorted(created.items())],
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _changed_meanwhile()
    return ok(data)
