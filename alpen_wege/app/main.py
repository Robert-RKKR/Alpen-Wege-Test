# Standard library
import logging
import uuid
from contextlib import asynccontextmanager

# Third-party
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Local application
from app.database import async_engine, create_tables
from app.redis import init_redis, close_redis, get_redis_pool
from app.profile.middleware import TokenRefreshMiddleware
from app.profile.routes import auth_router
from app.profile.routes import users_router
from app.explorer.routes import router as explorer_router
from app.core.routes import router as core_router
from app.compendium.routes import router as compendium_router
from app.core.utils.responses import fail, request_id_ctx

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
    yield
    await close_redis()
    await async_engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Alpen Wege", version="0.1.0", lifespan=lifespan)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(TokenRefreshMiddleware)

    # ---- Exception handlers ----

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
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
                error_message=f"{len(errors)} validation error(s)",
                errors=errors,
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

    api_v1_prefix = "/api/v1"
    app.include_router(auth_router, prefix=api_v1_prefix)
    app.include_router(users_router, prefix=api_v1_prefix)
    app.include_router(explorer_router, prefix=api_v1_prefix)
    app.include_router(core_router, prefix=api_v1_prefix)
    app.include_router(compendium_router, prefix=api_v1_prefix)

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
