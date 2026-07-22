from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.database import async_engine, create_tables
from app.redis import init_redis, close_redis, get_redis_pool
from app.auth.middleware import TokenRefreshMiddleware
from app.auth.routes import router as auth_router
from app.users.routes import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    await create_tables()
    yield
    await close_redis()
    await async_engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Alpen Wege", version="0.1.0", lifespan=lifespan)

    app.add_middleware(TokenRefreshMiddleware)

    api_v1_prefix = "/api/v1"
    app.include_router(auth_router, prefix=api_v1_prefix)
    app.include_router(users_router, prefix=api_v1_prefix)

    @app.get("/health")
    async def health():
        from app.database import AsyncSessionLocal

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

        return {
            "status": "ok",
            "database_tables": table_count,
            "redis_connected": redis_ok,
        }

    return app


app = create_app()
