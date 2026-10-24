from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.compendium.schemas.post import PostRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER


@router.get("", response_model=ApiResponse[list[PostRead]])
async def list_posts(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("post", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatPost)
    count_stmt = apply_scope(count_stmt, CompendiumCatPost, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatPost).options(*EAGER).order_by(CompendiumCatPost.name).limit(limit).offset(offset)
    stmt = apply_scope(stmt, CompendiumCatPost, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)
