# Standard library
from contextlib import asynccontextmanager

# Third-party
from fastapi import FastAPI
from sqlalchemy import text

# Local application
from app.database import async_engine, create_tables
from app.redis import init_redis, close_redis, get_redis_pool
from app.auth.middleware import TokenRefreshMiddleware
from app.auth.routes import router as auth_router
from app.users.routes import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application lifespan handler: startup runs before `yield`, shutdown after.
    # Params:
    #   app: the FastAPI application instance (required by the lifespan protocol).
    # Yields: control back to FastAPI while the app is running.
    # Startup: connect Redis and ensure database tables/extensions exist.
    await init_redis()
    await create_tables()
    yield
    # Shutdown: close Redis and dispose of the database engine's connection pool.
    await close_redis()
    await async_engine.dispose()


def create_app() -> FastAPI:
    # Application factory: build and configure the FastAPI instance.
    # Params: none.
    # Returns: the fully configured FastAPI application.
    app = FastAPI(title="Alpen Wege", version="0.1.0", lifespan=lifespan)

    # Rotate access tokens on every successful authenticated request.
    app.add_middleware(TokenRefreshMiddleware)

    # Mount the feature routers under a shared versioned API prefix.
    api_v1_prefix = "/api/v1"
    app.include_router(auth_router, prefix=api_v1_prefix)
    app.include_router(users_router, prefix=api_v1_prefix)

    @app.get("/health")
    async def health():
        # Health-check endpoint reporting database and Redis connectivity.
        # Params: none.
        # Returns: a dict with overall status, table count, and Redis connectivity.
        from app.database import AsyncSessionLocal

        # Query the number of public tables as a basic database liveness check.
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            table_count = result.scalar()

        # Ping Redis; treat any failure as "not connected" rather than erroring out.
        try:
            redis = get_redis_pool()
            await redis.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

        return {
            "status": "ok",
            "database_tables": table_count,
            "redis_connected": redis_ok,
        }

    return app


app = create_app()
