# Standard library
import logging
import uuid
from contextlib import asynccontextmanager

# Third-party
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

# Local application
from app.database import async_engine, create_tables
from app.redis import init_redis, close_redis, get_redis_pool
from app.profile.middleware import TokenRefreshMiddleware
from app.profile.routes import router as profile_router
from app.explorer.routes import router as explorer_router
from app.core.routes import router as core_router
from app.compendium.routes import router as compendium_router
from app.management.routes import router as management_router
from app.assets.routes import router as assets_router
from app.management.utils.event_logger import load_entity_type_cache
from app.management.utils.seed_entity_types import seed_entity_types
from app.core.utils.api_paths import API_V1
from app.core.utils.integrity import is_missing_icon
from app.core.utils.responses import AppError, fail, request_id_ctx
from app.core.utils.upload_limit import UploadSizeLimitMiddleware

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    await create_tables()
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        await seed_entity_types(session)
        await load_entity_type_cache(session)
        # after the entity types: PATCH /management/settings logs through the entity cache
        from app.management.runtime_settings.seed import seed_settings
        await seed_settings(session)
    yield
    await close_redis()
    await async_engine.dispose()


# Shown at the top of Swagger (/docs) and ReDoc (/redoc).
API_DESCRIPTION = """
REST API of Alpen Wege. Every URL is `/api/v1/{app}/{resource}` (apps: `profile`, `core`, `compendium`, `explorer`, `assets`, `management`).

**Login.** `POST /api/v1/profile/auth/login`, then press *Authorize* and paste the `access_token`. A token lasts a few minutes;
when it is half used up the answer carries a fresh one in the header `X-Access-Token`: use that one from then on.

**Answers.** Every answer has `response_status`, `response_code`, `response_message`, `response_data`, `response_details`
(`error_message`, `error_errors` on a failure) and `response_request_id`. A list answer also has `response_pagination`
(`pagination_total` counts the rows that match the filters).

**Lists (`GET` of a collection).**
`limit` and `offset` page through the rows (the users list calls the offset `skip`). Defaults: `limit` 1000, 100 on tracks, the
event log, jobs and my jobs; tracks, jobs and my jobs allow at most 500 per call. `sort=name` sorts ascending, `sort=-name`
descending (the allowed names are in the description of `sort`). Every list has filters that fit its data (text search `q`,
ids, `..._min` / `..._max`, `..._from` / `..._to`, `bbox`, `near`); filters are combined with AND, an id filter can be repeated
(`compendium_type_id=a&compendium_type_id=b`), and they only narrow what the caller may already see.
A value the database cannot take (a negative `limit`, a date in the year 9999, a NUL character) answers 422.

**Depth of one object (`GET .../{id}`).** Linked objects come as IDs. `expand=main_region.country,created_by` fills the ones
you name (3 levels deep, 10 links at most; a wrong name answers 400 and lists the allowed ones).

**Icons and flags.** An icon is an SVG picture kept in the database (`/assets/icons`). Reference values (sport types, rarities, ...),
resource types, countries and regions point to one with `icon_id`; countries use the icon `flag_<iso code>` (`flag_at`). The picture is
`GET /assets/icons/{id}/file`, or `/assets/icons/by-key/{key}/file`; add `?format=png&size=64` for a PNG. Everybody who is logged in
reads icons, only the administrator writes them. An uploaded SVG is cleaned (script, style, external links are removed and listed in
`response_details.removed`). `POST /assets/icons/upload-csv` creates many icons from one CSV (try `dry_run=true` first) and `POST /assets/icons/link`
sets `icon_id` on the rows whose icon text or code matches an icon key. An unknown `icon_id` answers 422. The text column `icon` still exists and is unchanged.

**Jobs.** Uploading a track and the rescan / reprocess endpoints answer 202 with a `job_id` (and a `Location` header);
follow it with `management/my-jobs/{job_id}` or the WebSocket `management/ws`.
"""

def create_app() -> FastAPI:
    app = FastAPI(title="Alpen Wege", version="0.1.0", description=API_DESCRIPTION, lifespan=lifespan)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TokenRefreshMiddleware)
    app.add_middleware(UploadSizeLimitMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)   # a list of 100 rows shrinks to about a tenth

    # ---- Exception handlers ----

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        if isinstance(exc, AppError):
            return JSONResponse(
                status_code=exc.status_code,
                content=fail(
                    exc.status_code,
                    exc.response_message,
                    error_message=exc.error_message,
                    errors=exc.error_errors or None,
                ),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.status_code, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err["loc"] if loc != "body")
            errors.append(
                {"field": field or None, "code": err["type"], "message": err["msg"]}
            )
        return JSONResponse(
            status_code=422,
            content=fail(
                422,
                "Validation failed",
                error_message=f"The request contains {len(errors)} invalid field(s). Check error_errors for details.",
                errors=errors,
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exc_handler(request: Request, exc: IntegrityError):
        # An icon_id that names no icon (any of the 22 tables with the column) is the caller's mistake: 422, like the
        # photo link. Every other integrity error is raised again and ends as before (500 from the handler below).
        if not is_missing_icon(exc):
            raise exc
        return JSONResponse(
            status_code=422,
            content=fail(
                422,
                "Validation failed",
                error_message="icon_id: the icon does not exist.",
                errors=[{"field": "icon_id", "code": "icon_not_found", "message": "The icon does not exist."}],
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(request: Request, exc: Exception):
        rid = request_id_ctx.get("")
        logger.error("Unhandled exception [request_id=%s]: %s", rid, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=fail(
                500,
                "Internal server error",
                error_message="An unexpected error occurred. Reference the request id when contacting support.",
            ),
        )

    # ---- Routers ----

    api_v1_prefix = API_V1
    app.include_router(profile_router, prefix=api_v1_prefix)
    app.include_router(explorer_router, prefix=api_v1_prefix)
    app.include_router(core_router, prefix=api_v1_prefix)
    app.include_router(compendium_router, prefix=api_v1_prefix)
    app.include_router(management_router, prefix=api_v1_prefix)
    app.include_router(assets_router, prefix=api_v1_prefix)

    @app.get("/health")
    async def health():
        from app.database import AsyncSessionLocal
        from app.core.utils.responses import ok

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            table_count = result.scalar()

        try:
            redis = get_redis_pool()
            await redis.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

        return ok({
            "status": "ok",
            "database_tables": table_count,
            "redis_connected": redis_ok,
        })

    return app


app = create_app()
