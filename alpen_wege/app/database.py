from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

settings = get_settings()

async_engine = create_async_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=5, max_overflow=10)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


@event.listens_for(sync_engine, "connect")
def _create_postgis_extension(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS moddatetime")
    cursor.close()
    dbapi_connection.commit()


async def create_tables():
    from app.core.base import Base
    # Force import all models so they register with Base.metadata
    import app.users.models  # noqa: F401
    import app.core.models  # noqa: F401
    import app.assets.models  # noqa: F401
    import app.compendium.models  # noqa: F401
    import app.explorer.models  # noqa: F401
    import app.profile.models  # noqa: F401
    import app.social.models  # noqa: F401
    import app.auth.models  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS moddatetime"))
        await conn.run_sync(Base.metadata.create_all)
