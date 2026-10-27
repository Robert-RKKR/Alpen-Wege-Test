#!/usr/bin/env python
"""Option B of decision 2: an expanded user shows only id and username, except to administrators and to the user
himself. Applied on top of apply_expand.py, on the same copy.

    python apply_viewer.py REPO_COPY
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def stop(message):
    raise SystemExit(f"STOP: {message}")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    with open(ROOT / rel, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def sub_once(rel, old, new):
    text = read(rel)
    if text.count(old) != 1:
        stop(f"{rel}: expected exactly one of {old!r}, found {text.count(old)}")
    write(rel, text.replace(old, new))


# 1. the schema of the expanded user
sub_once("app/profile/schemas/user_read.py", "from datetime import date, datetime\n", "from datetime import date, datetime\nfrom typing import ClassVar\n")
sub_once("app/profile/schemas/user_read.py", '''# The user object that expanded responses return for created_by, changed_by, updated_by and user. One alias, so the
# rule "who sees which user fields" can be changed in one place.
ExpandedUser = UserRead
''', '''class UserExpandedRead(UserRead):
    # The user object in expanded responses (created_by, changed_by, updated_by, user). Everybody sees id and
    # username; the other fields are only for administrators and for the user himself, everybody else gets null.
    PUBLIC_FIELDS: ClassVar[tuple[str, ...]] = ("id", "username")

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    height_cm: int | None = None
    max_heart_rate: int | None = None
    resting_heart_rate: int | None = None
    is_active: bool | None = None
    created_at: datetime | None = None
    last_active_at: datetime | None = None

    @classmethod
    def redact(cls, data: dict, viewer) -> dict:
        # Called by ExpandPlan.render for every expanded user. No viewer means the safe answer: only the public fields.
        if viewer is not None and (viewer.id == data["id"] or viewer.user_group == "administrator"):
            return data
        return {name: (value if name in cls.PUBLIC_FIELDS else None) for name, value in data.items()}


# The user object that expanded responses return. One alias, so the rule "who sees which user fields" can be
# changed in one place.
ExpandedUser = UserExpandedRead
''')

# 2. the helper hands the viewer to the hook of the schema
sub_once("app/core/utils/expand.py",
         "def _render(schema: type[BaseModel], obj: Any, tree: dict[str, _Node], extra: dict[str, Any]) -> dict[str, Any]:\n",
         "def _render(schema: type[BaseModel], obj: Any, tree: dict[str, _Node], extra: dict[str, Any], viewer: Any) -> dict[str, Any]:\n")
sub_once("app/core/utils/expand.py",
         "        out[name] = None if child is None else _render(info.target, child, node.children, {})\n"
         "    for name, value in extra.items():\n        out.setdefault(name, value)\n    return out\n",
         "        out[name] = None if child is None else _render(info.target, child, node.children, {}, viewer)\n"
         "    for name, value in extra.items():\n        out.setdefault(name, value)\n"
         "    redact = getattr(schema, \"redact\", None)    # a schema may hide fields from some viewers (the expanded user)\n"
         "    return redact(out, viewer) if redact else out\n")
sub_once("app/core/utils/expand.py",
         "    def render(self, obj: Any, **extra: Any) -> dict[str, Any]:\n"
         "        # Object -> dict for the response model; links that were not requested are None. extra gives values for\n"
         "        # fields the object does not have (computed fields) and keys that a schema validator reads.\n"
         "        return _render(self.schema, obj, self.tree, extra)\n",
         "    def render(self, obj: Any, viewer: Any = None, **extra: Any) -> dict[str, Any]:\n"
         "        # Object -> dict for the response model; links that were not requested are None. viewer is the user who\n"
         "        # asks (schemas such as the expanded user hide fields from other viewers). extra gives values for fields\n"
         "        # the object does not have (computed fields) and keys that a schema validator reads.\n"
         "        return _render(self.schema, obj, self.tree, extra, viewer)\n")

# 3. every route passes the user who asks
routes = sorted(p for p in (ROOT / "app").glob("*/routes/**/get_one.py")) + [ROOT / "app/management/routes/event_log/compare.py"]
changed = 0
for path in routes:
    rel = str(path.relative_to(ROOT))
    text = read(rel)
    if "plan.render(" not in text:
        continue
    if "access: AccessContext" in text:
        viewer = "access.user"
    elif re.search(r"^\s+_admin: ProfileUsrUser", text, re.M):
        viewer = "_admin"
    elif re.search(r"^\s+_user: ProfileUsrUser", text, re.M):
        viewer = "_user"
    else:
        stop(f"{rel}: cannot tell who asks")
    new, n = re.subn(r"plan\.render\((\w+)", rf"plan.render(\1, viewer={viewer}", text)
    if n == 0:
        stop(f"{rel}: no plan.render call changed")
    write(rel, new)
    changed += 1
print(f"done: {changed} route file(s) pass the viewer")


# 4. README: the visibility row
sub_once("README.md",
         "| Who sees what | Whoever may read an object may see what is expanded inside it, including the whole profile "
         "(email, birth date, heart rates) of the user behind `created_by`, `changed_by`, `updated_by` or `user` |\n",
         "| Who sees what | Whoever may read an object may see what is expanded inside it. Of a user behind `created_by`, "
         "`changed_by`, `updated_by` or `user` everybody sees `id` and `username`; the other profile fields (email, birth date, "
         "heart rates, ...) are `null` unless the caller is an administrator or that user himself |\n")
print("done: README row of option B")
