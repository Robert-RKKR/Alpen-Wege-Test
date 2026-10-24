from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.compendium.schemas.post import PostRead

from ._router import router
from ._shared import EAGER


@router.get("/{post_id}", response_model=ApiResponse[PostRead])
async def get_post(
    post_id: UUID,
    access: AccessContext = Depends(resource_access("post", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == post_id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Post not found")
    return ok(obj)
