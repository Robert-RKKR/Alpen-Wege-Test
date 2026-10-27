#!/usr/bin/env python
"""Filters, sorting and paging on every list GET (get_filters_implementation_plan.md).

    python apply_filters.py REPO_COPY [--gzip]

Run it on a scratch copy of the repo, never on the repo itself. It is guarded: every file it replaces must still be
in the state of the delivered repo (2026-10-26); if one is not, it stops before it writes that file.

What it does
  1. app/core/utils/listing.py                the helper (new file)
  2. 20 reference-table list routes           written from one template, checked against the old text
  3. 15 other list routes                     replaced by the explicit files next to this script (files/)
  4. app/main.py                              GZipMiddleware (only with --gzip; off by default)
  5. scripts/route_map.py                     compare --lists
  6. tests, live check, README                copied / patched
"""
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(ARGS) != 1:
    raise SystemExit(__doc__)
ROOT = Path(ARGS[0]).resolve()
GZIP = "--gzip" in sys.argv


def stop(message):
    raise SystemExit(f"STOP: {message}")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def sub_once(rel, old, new):
    text = read(rel)
    if text.count(old) != 1:
        stop(f"{rel}: expected exactly one of {old[:70]!r}, found {text.count(old)}")
    write(rel, text.replace(old, new))


if not (ROOT / "app/main.py").is_file():
    stop(f"{ROOT} is not the repo root")

# ---------------------------------------------------------------- 1. the helper
if (ROOT / "app/core/utils/listing.py").exists():
    stop("app/core/utils/listing.py exists: the filters are already applied")
shutil.copyfile(HERE / "listing.py", ROOT / "app/core/utils/listing.py")
print("1. app/core/utils/listing.py written")

# ---------------------------------------------------------------- 2. reference tables
OLD_REF = '''from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import {model}
from app.core.schemas.ref import {schema}

from ._router import router


@router.get("", response_model=ApiResponse[list[{schema}]])
async def list_items(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("ref", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from({model})
    if access.scope == "own":
        count_stmt = count_stmt.where({model}.created_by == access.user.id)
    total = (await db.execute(count_stmt)).scalar()

    stmt = select({model}).order_by({model}.name).limit(limit).offset(offset)
    if access.scope == "own":
        stmt = stmt.where({model}.created_by == access.user.id)
    result = await db.execute(stmt)
    return ok_list(result.scalars().all(), total=total, limit=limit, offset=offset)
'''

NEW_REF = '''from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import NameFilters, Page, Sort, page_params, sort_params
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import {model}
from app.core.schemas.ref import {schema}

from ._router import router

M = {model}
SORT = {{"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at{factor}}}


@router.get("", response_model=ApiResponse[list[{schema}]])
async def list_items(
    access: AccessContext = Depends(resource_access("ref", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: NameFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M), M)
    if access.scope == "own":
        base = base.where(M.created_by == access.user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
'''

NEW_COMPENDIUM_TYPE = '''from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    NameFilters, Page, Sort, equals, page_params, search_query, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefCompendiumType
from app.core.schemas.ref import CompendiumTypeRead

from ._router import router

M = CoreRefCompendiumType
SORT = {"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at, "point_factor": M.point_factor}


class CompendiumTypeFilters(NameFilters):
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        created_by: UUID | None = Query(None, description="Rows created by this user."),
        is_collectable: bool | None = Query(None, description="Only the types that can be collected (true) or not (false)."),
    ):
        super().__init__(q, created_by)
        self.is_collectable = is_collectable

    def apply(self, stmt, model):
        return where_all(super().apply(stmt, model), equals(model.is_collectable, self.is_collectable))


@router.get("", response_model=ApiResponse[list[CompendiumTypeRead]])
async def list_items(
    access: AccessContext = Depends(resource_access("ref", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: CompendiumTypeFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M), M)
    if access.scope == "own":
        base = base.where(M.created_by == access.user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
'''

NEW_DIFFICULTY_SPORT = '''from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    NameFilters, Page, Sort, ids_query, one_of, page_params, search_query, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefDifficultySport
from app.core.schemas.ref import DifficultySportRead

from ._router import router

M = CoreRefDifficultySport
SORT = {"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at, "point_factor": M.point_factor}


class DifficultySportFilters(NameFilters):
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        created_by: UUID | None = Query(None, description="Rows created by this user."),
        sport_type_id: list[UUID] | None = ids_query("Sport type"),
    ):
        super().__init__(q, created_by)
        self.sport_type_id = sport_type_id

    def apply(self, stmt, model):
        return where_all(super().apply(stmt, model), one_of(model.sport_type_id, self.sport_type_id))


@router.get("", response_model=ApiResponse[list[DifficultySportRead]])
async def list_items(
    access: AccessContext = Depends(resource_access("ref", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: DifficultySportFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M), M)
    if access.scope == "own":
        base = base.where(M.created_by == access.user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
'''
NEW_COMPENDIUM_TYPE = "from uuid import UUID\n\n" + NEW_COMPENDIUM_TYPE

ref_done = 0
for path in sorted((ROOT / "app/core/routes/ref").glob("*/get_many.py")):
    rel = str(path.relative_to(ROOT))
    folder = path.parent.name
    if folder == "resource_type":
        continue   # a different file (administrators only), replaced in step 3
    text = read(rel)
    found = re.search(r"from app\.core\.models\.models_ref import (\w+)\nfrom app\.core\.schemas\.ref import (\w+)\n", text)
    if not found:
        stop(f"{rel}: not the expected reference-table list route")
    model, schema = found.groups()
    if text != OLD_REF.format(model=model, schema=schema):
        stop(f"{rel}: differs from the delivered reference-table list route")
    if folder == "compendium_type":
        new = NEW_COMPENDIUM_TYPE
    elif folder == "difficulty_sport":
        new = NEW_DIFFICULTY_SPORT
    else:
        factor = ', "point_factor": M.point_factor' if schema != "RefBaseRead" else ""
        new = NEW_REF.format(model=model, schema=schema, factor=factor)
    write(rel, new)
    ref_done += 1
print(f"2. {ref_done} reference-table list routes rewritten")

# ---------------------------------------------------------------- 3. the explicit files
copied = 0
for src in sorted((HERE / "files").rglob("get_many.py")):
    rel = str(src.relative_to(HERE / "files")).replace("\\", "/")
    if not (ROOT / rel).is_file():
        stop(f"{rel}: the route does not exist in the repo")
    old = read(rel)
    if "page_params" in old:
        stop(f"{rel}: already uses page_params")
    if "ok_list(" not in old or "limit" not in old:
        stop(f"{rel}: not a list route")
    shutil.copyfile(src, ROOT / rel)
    copied += 1
print(f"3. {copied} explicit list routes written")

# ---------------------------------------------------------------- 4. gzip
if GZIP:
    sub_once("app/main.py", "from starlette.middleware.base import BaseHTTPMiddleware\n",
             "from starlette.middleware.base import BaseHTTPMiddleware\nfrom starlette.middleware.gzip import GZipMiddleware\n")
    sub_once("app/main.py", "    app.add_middleware(UploadSizeLimitMiddleware)\n",
             "    app.add_middleware(UploadSizeLimitMiddleware)\n"
             "    app.add_middleware(GZipMiddleware, minimum_size=1000)   # a list of 100 rows shrinks to about a tenth\n")
    print("4. GZipMiddleware added")
else:
    print("4. gzip not added (use --gzip to add it)")

# ---------------------------------------------------------------- 5. route_map compare --lists
shutil.copyfile(HERE / "route_map_lists.patch.py", ROOT / ".route_map_patch.py")   # removed below
exec(compile((ROOT / ".route_map_patch.py").read_text(encoding="utf-8"), "route_map_patch", "exec"), {"ROOT": ROOT, "sub_once": sub_once, "stop": stop, "GZIP": GZIP})
(ROOT / ".route_map_patch.py").unlink()
print("5. route_map.py: compare --lists")

# ---------------------------------------------------------------- 6. tests, live check, README
for rel in ("tests/test_listing.py", "tests/test_list_routes.py", "scripts/list_check.py"):
    shutil.copyfile(HERE / Path(rel).name, ROOT / rel)
print("6. tests and live check copied")
text = (HERE / "readme_section.md").read_text(encoding="utf-8")
sub_once("README.md", "## CSV bulk import\n", text + "\n---\n\n## CSV bulk import\n")
print("   README section added")
print("done")
