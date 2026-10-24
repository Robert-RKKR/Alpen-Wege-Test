# Third-party
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

# Local application
from app.config import get_settings

# Cached application settings (database URLs, pool sizing).
settings = get_settings()

# Async engine + session factory used by the FastAPI request path.
async_engine = create_async_engine(
    settings.DATABASE_URL, pool_size=10, max_overflow=20
)
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

# Sync engine + session factory used by Celery workers and offline scripts.
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC, pool_size=5, max_overflow=10
)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


@event.listens_for(sync_engine, "connect")
def _create_postgis_extension(dbapi_connection, connection_record):
    # SQLAlchemy "connect" hook: ensure required PostgreSQL extensions exist.
    # Runs each time a new raw connection is established on the sync engine.
    # Params:
    #   dbapi_connection: the raw DB-API connection just opened.
    #   connection_record: SQLAlchemy's bookkeeping record (unused here).
    # Returns: nothing.
    # Create the extensions if they are not already installed, then commit.
    cursor = dbapi_connection.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS moddatetime")
    cursor.close()
    dbapi_connection.commit()


async def create_tables():
    # Create all database tables (and required extensions) from the ORM
    # metadata.
    # Called once on application startup.
    # Params: none.
    # Returns: nothing.
    from app.core.base import Base

    # Force import all models so they register with Base.metadata
    import app.core.models  # noqa: F401
    import app.management.models  # noqa: F401
    import app.assets.models  # noqa: F401
    import app.compendium.models  # noqa: F401
    import app.explorer.models  # noqa: F401
    import app.profile.models  # noqa: F401
    import app.social.models  # noqa: F401

    # Open a transaction, ensure extensions exist, then emit CREATE TABLE for
    # all models.
    async with async_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS moddatetime"))
        await conn.run_sync(Base.metadata.create_all)
