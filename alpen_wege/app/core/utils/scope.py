# Standard library
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.profile.permissions import AccessContext


def apply_scope(stmt, model, access: "AccessContext"):
    # Narrow a SELECT to the rows the caller may see:
    #   "own"    -> rows created by the caller
    #   "public" -> rows created by the caller or marked is_public
    #   "all"    -> no filter
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)  # noqa: E712
        )
    return stmt
