# Standard library
from collections.abc import AsyncGenerator

# Third-party
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # FastAPI dependency that yields a database session with transaction handling.
    # Params: none.
    # Yields: an AsyncSession for use during the request.
    # Behavior: commits when the request handler succeeds, rolls back on any exception.
    async with AsyncSessionLocal() as session:
        try:
            # Hand the session to the route handler.
            yield session
            # Handler returned normally -> commit the transaction.
            await session.commit()
        except Exception:
            # Any error -> roll back and re-raise so the error propagates.
            await session.rollback()
            raise
