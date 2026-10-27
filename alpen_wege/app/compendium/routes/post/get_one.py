from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.compendium.schemas.post import PostDetail

from ._router import router


@router.get("/{post_id}", response_model=ApiResponse[PostDetail])
async def get_post(
    post_id: UUID,
    access: AccessContext = Depends(resource_access("post", "read")),
    plan: ExpandPlan = Depends(expand_plan(PostDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == post_id)
        .options(*plan.load_options(CompendiumCatPost))
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Post not found")
    return ok(plan.render(obj, viewer=access.user))
