# GET `?expand=` — implementation plan (for VS Code Claude)

> **Superseded on 2026-10-24 by `get_expand_implementation_plan_v2.md`.** This v1 was written before the routes were restructured (folder per resource, URLs `/api/v1/{app}/{resource}`) and before tracks, jobs and settings existed; its file paths, URLs and the list of endpoints are outdated. Use v2.

> Update 2026-10-23: the management app moves the event log. If this plan is not merged yet, read `app/core/{models,schemas,routes}/event_log.py` as `app/management/{models,schemas,routes}/event_log.py`, `CoreLogEvent` as `MgmtLogEvent`, and `/event-log...` as `/management/event-log...` (table in `management_implementation_plan.md`, section 5.3). The move is already done in the repo.

Version 1 · written 2026-10-21 · status: ready to implement, not started
Review: two independent reviews on 2026-10-21 (library mechanics; fit with the real repo). The reference code was traced by hand and checked against library documentation, but never run. All reported blockers and "should fix" items are applied.
Decisions this plan implements: `get_expand_decisions.md` (same folder). If the two disagree, ask the user.

**Plain-English summary (for the user).** Today a single-object GET such as `GET /pois/{id}` always returns some linked objects (type, region) and only IDs for others (`created_by`). After this work, every single-object GET returns **only IDs by default**. You add `?expand=` with a comma-separated list of links to get the full linked object instead, for example `?expand=changed_by` on a log entry, or `?expand=main_region.country,created_by` on a POI. A dotted path may go at most 3 levels deep, and a request may expand at most 10 links in total. List endpoints, POST, PATCH and DELETE do not change. No database change is needed.

---

## 0. Rules for the implementing agent (read first)

1. **Work milestone by milestone** (E0 to E6, section 4). After each milestone: run its checks, write the result into the "Execution log" at the end of this file, then **stop and report to the user**. Do not start the next milestone until the user says go.
2. **Scope.** Change only the single-object GET routes listed in section 5. Do **not** touch list GETs, POST, PATCH, DELETE, `upload-csv`, `/auth/*`, `/users/*`, and do **not** edit any existing `*Read`, `*Create` or `*Update` schema. New `*Detail` schemas are added next to the `*Read` schemas.
3. **No database changes.** Only Python relationships (read-only links between model classes) and schemas are added. No new table, column, migration or DDL. Tables are created by `create_all` at startup and are not affected.
4. **If the code differs from this plan** (file moved, different signature, different name), stop and report. Do not improvise. Small naming deviations go into the execution log.
5. **The code in this plan has never been executed.** When it was written, the Cowork sandbox could not run code (Windows update problem). Every snippet, including Appendix A, is reference code. The tests in E1 and E3 are what prove it. If a test fails, fix the code. Change a test only if the test itself is wrong, and say why in the log.
6. **Style.** Match the surrounding file: import groups with the comments `# Standard library`, `# Third-party`, `# Local application` where the file already uses them, 4 spaces, double quotes, type hints like `X | None`. Short comments that explain why, not what.
7. **Never expose secrets.** `ProfileUserCredentials` (password hash) must not appear in any schema. A test enforces this.
8. **The repository does not look like a git repo**, so make the backup in E0 before editing anything.
9. **Running commands.** If you can run shell commands, run the ones in each milestone. If you cannot, give the user the exact command and ask for the output. Commands are meant to run on the Docker host from the project root. The `api` container bind-mounts the project folder and runs `uvicorn --reload`, so saved edits go live immediately. A broken import shows up as a traceback in `sudo docker logs --tail 50 alpen-api`.
10. **Access tokens are short-lived and rotate.** `.env` sets `JWT_EXPIRE_MINUTES=5`. After half of that time, the first successful request returns a new token in the response header `X-Access-Token` and **blacklists the old one** (`app/profile/middleware/token_refresh.py`). So every script (`baseline_snapshot.py`, `smoke_expand.py`) must (a) switch to `X-Access-Token` whenever a response carries it, and (b) log in again once and retry when it gets a 401. For manual `curl` runs, repeat the `TOKEN=$(...)` login line before each block; a 401 simply means "log in again".
11. **Do not touch `requirements.txt` and do not rebuild the images during this work.** Library versions are not pinned, so a rebuild can silently upgrade them. If a rebuild happens anyway, run E0 step 2 again and compare with the logged versions.

---

## 1. Contract: what the API does after this work

### 1.1 Behaviour

| Request | Result |
|---|---|
| `GET /event-log/{id}` | `changed_by` = UUID. `changed_by_user` = `null`. `entity_type` = `null` (`entity_type_id` is always present). |
| `GET /event-log/{id}?expand=changed_by` | `changed_by_user` = the full user object (same fields as `GET /users/me`). |
| `GET /event-log/{id}?expand=changed_by,entity_type` | Both resolved. |
| `GET /pois/{id}` | IDs only. `compendium_type`, `main_region`, `created_by_user` are `null`. |
| `GET /pois/{id}?expand=main_region.country,main_region.region_type,compendium_type,created_by` | Nested objects, 3 levels at most per path. Parents of a path are included automatically. |
| `GET /pois/{id}?expand=main_region.country.created_by` | Accepted: 3 levels (`main_region`, `country`, `created_by`). |
| `GET /pois/{id}?expand=main_region.parent.parent.country` | **400**: 4 levels. The depth is checked before the names. |
| `GET /pois/{id}?expand=nope` | **400** with the list of allowed names at that level. |
| `GET /pois/{id}?expand=` (empty) | Same as no `expand`. |
| `GET /pois` (list), POST, PATCH, DELETE | **Unchanged.** Lists keep returning their nested objects as today. |

### 1.2 Rules (all confirmed by the user, see `get_expand_decisions.md`)

- **ID only by default.** Nothing is expanded unless requested, including the links that are always expanded today (`compendium_type`, `main_region`, `poi`, `rarity`, `country`, `parent`, `region_type`, `post_type`, `region`, `entity_type`).
- **Expanded means full.** The linked object is returned with all the fields of its own `*Detail` schema. For a user that is the `UserRead` shape (email, birth date, heart rates, `user_group` and so on, never the password hash).
- **Visibility.** If the caller may read the object, the caller may see everything expanded inside it. No extra permission check per expanded child.
- **Where the object goes.** Next to the ID, in a sibling field. Existing names stay (`compendium_type`, `main_region`, ...). For users the field is `created_by_user` / `changed_by_user`, while the name used in `?expand=` is `created_by` / `changed_by`.
- **Unrequested links are present with the value `null`.** The JSON shape is stable. `null` also appears when the link is requested but the foreign key itself is `null` (for example a region without a parent).
- **Limits.** A dotted path has at most 3 segments. A request has at most 10 distinct links in total (shared parents count once). Both limits answer with 400.
- **Errors.** Status 400, `response_message` is just "Bad request". The useful text is in `response_details.error_message` (it lists the allowed names), and `response_details.error_errors` has one entry `{"field": "expand", "code": "invalid_expand", "message": ...}`.
- **One parameter, commas.** Write `?expand=a,b`. Repeating the parameter (`?expand=a&expand=b`) is not supported; only the last value is used.

### 1.3 Example (POI)

Default:

```json
{ "id": "…", "name": "Zugspitze", "compendium_type_id": "…", "compendium_type": null,
  "main_region_id": "…", "main_region": null, "created_by": "…", "created_by_user": null }
```

`?expand=main_region.country,created_by`:

```json
{ "id": "…", "name": "Zugspitze", "compendium_type": null,
  "main_region_id": "…",
  "main_region": { "id": "…", "name": "Wetterstein", "country_id": "…",
                   "country": { "id": "…", "name": "Germany", "iso_code": "DE", "created_by_user": null },
                   "region_type": null, "parent": null, "created_by_user": null },
  "created_by": "…",
  "created_by_user": { "id": "…", "username": "admin", "email": "admin@alpenwege.dev", "user_group": "administrator" } }
```

---

## 2. Design

### 2.1 Four building blocks

1. **`Link()` marker** (new file `app/core/utils/expand.py`). A field of a `*Detail` schema declared with `Link()` is an expandable link. The nested schema is read from the field's type, so nothing is declared twice.
2. **`ExpandPlan`** (same file). `ExpandPlan.parse(schema, "a.b,c")` validates the names against the schema, enforces the limits and builds a tree. `plan.load_options(Model)` returns SQLAlchemy `selectinload` options, one extra small SELECT per requested link. `plan.render(obj)` turns the ORM object into a plain dict and reads **only the requested links**.
3. **`*Detail` schemas.** For each single GET, a subclass of the existing `*Read` schema. Link fields are redeclared as `X | None = Link()`. The new schema is used only as the `response_model` of the single GET. `*Read` stays for lists, POST and PATCH.
4. **Read-only relationships on the models** where none exist: `created_by_user` on every model with `CreatorMixin`, `changed_by_user` on `CoreLogEvent`, `company` and `gear_type` on gear, `sport_type` on difficulty-sport. They use `lazy="raise"` like the existing ones, so nothing is ever loaded by accident.

### 2.2 Data flow

```
GET /cards/{id}?expand=poi.main_region.country,created_by
  │  Depends(expand_plan(CardDetail))   -> ExpandPlan.parse   (400 on bad names, depth > 3, links > 10)
  ▼
  tree:  poi ─ main_region ─ country        created_by
  │  select(Card).options(*plan.load_options(Card))
  ▼
  SELECT card + SELECT poi + SELECT region + SELECT country + SELECT user (+ credentials, see section 3 item 5)
  │  check_object_access(...)             (unchanged)
  │  ok(plan.render(card))                -> plain dict; unrequested links are None
  ▼
  FastAPI validates the dict as ApiResponse[CardDetail] and returns JSON
```

### 2.3 Why this and not something simpler

- **Why not turn unrequested relationships off with `noload`.** If the same database row is reachable through two paths in one request (very likely: a POI's `main_region` is often also one of its `poi-regions`), SQLAlchemy keeps one object in memory and the first path wins. A `noload` on one path would silently leave `null` where the other path asked for data. `render()` reads only requested links, so this cannot happen. A smoke test in E5 proves it.
- **Why not let pydantic read the ORM object directly (as `ok(obj)` does today).** It reads every field, including relationships that are `lazy="raise"` and not loaded, which crashes. `render()` avoids that.
- **Why `*Detail` subclasses.** The same `*Read` classes are used by lists, POST and PATCH. Changing them would change those responses, which is out of scope. Subclasses leave them untouched.
- **Why a plain dict from `render()`.** FastAPI already validates the response against `response_model`. Returning a dict means one validation, and the geometry fields still work (`GeoPointField` converts the WKB value).

### 2.4 Out of scope (do not build)

List endpoints; `main_photo_id` and `poi_access_id` links (no photo or access read schema exists yet); resolving the object a log entry is about (`entity_id`, different table per entity type); IDs inside `snapshot`; any non-GET route; per-child permission checks; a generic `?depth=N`.

---

## 3. Facts about the current code this plan depends on

Verified by reading the code on 2026-10-21. If any is no longer true, stop and report.

1. **Single GET routes** (all return `ok(obj)` and use `response_model=ApiResponse[XRead]`):
   `app/compendium/routes/poi.py::get_poi`, `card.py::get_card`, `region.py::get_region`, `country.py::get_country`, `post.py::get_post`, `poi_region.py::get_poi_region`, `app/explorer/routes/gear.py::get_gear`, `app/core/routes/ref.py::get_item` (inside the factory `_build_ref_router`, 19 routers), `app/core/routes/event_log.py::get_event_log` and `compare_event_logs`. `/users/me`, `/users/{user_id}` and `/event-log/entity-types` are **not** in scope.
2. **Relationships are all `lazy="raise"`.** Routes load what the schema needs with a module-level `_EAGER = [selectinload(...)]` list. Keep `_EAGER`: lists, POST and PATCH still use it. Only the single GET stops using it.
3. **`CoreLogEvent.entity_type` is `lazy="joined"`** (`app/core/models/event_log.py`). It is joined on every query of that model. Leave it as is; the extra JOIN on a tiny table is harmless.
4. **`CreatorMixin`** (`app/core/base.py`) gives `created_by` (FK to `profile_usr_user.id`, NOT NULL) to 45 mapped classes (25 directly, the 19 `CoreRef*` reference tables through `ReferenceBaseMixin`, and `CoreRefResourceType`). No model that uses `CreatorMixin` also has a second FK to `profile_usr_user`, but the new relationship still names its foreign key explicitly.
5. **`ProfileUsrUser`** (`app/profile/models/user.py`) has no `user_group` attribute. The group lives on `credentials.user_group`. `UserRead` has `user_group: str | None = None`, and `_user_to_read` in `app/profile/routes/me.py` fills it by hand. Reading a user through pydantic `from_attributes` would therefore show `user_group: null` unless the model gets a property (E1). `ProfileUsrUser.credentials` is `lazy="selectin"`, so it loads automatically with every user.
6. **No relationships exist yet** for: `ExplorerAggGear.company` / `gear_type`, `CoreRefDifficultySport.sport_type`, `CoreLogEvent.changed_by_user`, and `created_by_user` anywhere.
7. **`GearRead` has no `created_by` field.** Detail schema adds it (section 5).
8. **Responses.** `ok(data)` in `app/core/utils/responses.py` returns the envelope dict. `AppError(status, message, *, error_message="", error_errors=None)` is rendered by the handler in `app/main.py` (field `response_details.error_errors`). Existing code already raises `AppError(400, "Bad request", error_message=...)`.
9. **Seeded access policies** (`scripts/init_seed.py`): users `admin@` / `editor@` / `viewer@` / `guest@alpenwege.dev`, password `!Password@5005`. Guest, viewer and editor have `read: all` on all compendium and ref resources, so **any registered account can read every POI, region, country, card, post and ref row, and with the user's confirmed rule can therefore expand `created_by` and see that creator's full profile (email, birth date, heart rates).** Explorer resources are `read: public` for guest, viewer and editor, so the same holds for any public gear row created by an **ordinary user**: `GET /gear/{id}?expand=created_by` shows that user's email, birth date and heart rates to everybody. Tracks and trips will behave the same when they get Detail schemas. The user accepted the rule. The code keeps it a one-line switch (`ExpandedUser` alias, Appendix A).
10. **No test framework** is installed (`requirements.txt` has no pytest) and there is no `tests/` folder. `test/` (singular) holds SQL files, docs, `generate_schema.py` and a compose file, and `test` is also a Python stdlib package name, so **new tests go in `tests/`** and use the stdlib `unittest`. The integration script uses only `urllib`.
11. **Docker.** Containers `alpen-api`, `alpen-celery`, `alpen-postgres`, `alpen-redis`. API on port 8000. Python 3.12. Library versions are not pinned (`fastapi>=0.111`, `sqlalchemy>=2.0.30`, `pydantic>=2.7`), so E0 records the installed versions.
12. **Imports are cycle-free for this change**: `app/profile/schemas/*.py` and `app/core/schemas/*.py` import nothing from `app.*`. So `app.core.schemas.ref` may import `app.core.utils.expand`, which imports `app.profile.schemas.user_read`.

---

## 4. Milestones

Naming: **E0 to E6** ("E" for expand). They are independent of the milestones M0 to M10 in `track_pipeline_implementation_plan.md`.

| Milestone | What | Behaviour change for API clients |
|---|---|---|
| E0 | Backup, versions, baseline snapshot | none |
| E1 | Helper, relationships, `user_group` property, unit tests | none |
| E2 | Event log pilot (`/event-log/{id}` and compare) | event log detail only |
| E3 | All other `*Detail` schemas and the missing relationships, wiring test | none (schemas not used by routes yet) |
| E4 | POI pilot (`/pois/{id}`) | POI detail only |
| E5 | Remaining single GETs (region, country, card, post, poi-regions, gear, ref) | those detail routes |
| E6 | README, OpenAPI check, regression, query count, cleanup | none |

### E0 — Backup, versions, baseline (no change inside `app/`)

1. **Backup.** Copy the `app/` folder and `README.md` outside the project. Linux host: `cp -a app ../app_before_expand && cp README.md ../README.before_expand.md`. PowerShell: `Copy-Item -Recurse app ..\app_before_expand; Copy-Item README.md ..\README.before_expand.md`.
2. **Record library versions** and paste them into the execution log:
   `sudo docker exec alpen-api pip list 2>/dev/null | grep -i -E "^(fastapi|starlette|pydantic|pydantic[-_]core|sqlalchemy|geoalchemy2|asyncpg) "`
   Stop and report if pydantic is below 2.7 or SQLAlchemy is below 2.0.30.
3. **Record OpenAPI size** before any change:
   `curl -s localhost:8000/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['paths']), len(d['components']['schemas']))"`
4. **Create `tests/__init__.py`** (empty) **and `tests/baseline_snapshot.py`.** Specification:
   - Standard library only (`urllib.request`, `json`, `pathlib`, `sys`, `os`). Base URL from env `API_BASE`, default `http://localhost:8000/api/v1`.
   - Logs in as `admin@alpenwege.dev` / `!Password@5005` (`POST /auth/login`, token in `response_data.access_token`). If login fails, print: `run: sudo docker exec alpen-api python /app/scripts/init_seed.py`.
   - Collections: `pois, cards, regions, countries, posts, poi-regions, gear, ref/companies, ref/gear-types, ref/sport-types, ref/difficulty-sports, ref/rarities, ref/compendium-types, ref/region-types, ref/post-types`.
   - For each collection: `GET /{c}?limit=5` saved to `tests/_baseline/{name}.list.json`; if the list has an item, `GET /{c}/{first id}` saved to `{name}.single.json`; the used ids go to `tests/_baseline/_ids.json`. `{name}` is the collection path with `/` replaced by `__` (for example `ref__rarities`). Normalize before saving: `response_request_id` becomes `"<rid>"`, keys sorted, 2-space indent.
   - Snapshot mode refuses to overwrite existing baseline files unless `--force` is given (so a later accidental run cannot erase the "before" state).
   - Print one line per collection with its row count, taken from `response_pagination.pagination_total` of the list response.
   - Token handling as in rule 10 (adopt `X-Access-Token`, re-login once on 401).
   - The event log is **not** part of the baseline (it changes with every write). It is covered by the smoke test.
   - Mode `--compare`: fetch the same ids again and print one line per file: `IDENTICAL` or `DIFFERENT`. `response_request_id` is ignored in every comparison. A difference in any `*.list.json` is a **failure**. For `*.single.json` a difference is allowed only when every baseline key still exists and every changed value was a nested object in the baseline and is now `null` (that is the intended change from E4 on); new keys are allowed (`created_by_user`). Exit code 1 on failure.
5. **Run it:** `sudo docker exec -w /app alpen-api python tests/baseline_snapshot.py`. Paste the printed row counts into the log (the user expects `cards` to be empty). The files are written by the container as root, so removing them later needs `sudo`.
6. **Health:** `curl -s localhost:8000/health` must show `redis_connected: true`.

**Done when:** backup exists, versions and counts are in the log, baseline files exist.

### E1 — Foundation (no behaviour change)

**Edits**

1. **New file `app/core/utils/expand.py`** — copy from Appendix A.
2. **`app/profile/models/user.py`** — add a property after the `credentials` relationship:

   ```python
       @property
       def user_group(self) -> str | None:
           # Lets an expanded user show its group like GET /users/me does. The
           # group is stored on the credentials row, which is always loaded
           # together with the user (lazy="selectin").
           return self.credentials.user_group if self.credentials else None
   ```
3. **`app/core/base.py`** — add `relationship` to the `from sqlalchemy.orm import (...)` list, and add this to `CreatorMixin` below `created_by`:

   ```python
       @declared_attr
       def created_by_user(cls):
           # Read-only link to the creating user. Not loaded unless a GET asks
           # for it with ?expand=created_by; lazy="raise" blocks accidental loads.
           return relationship(
               "ProfileUsrUser",
               foreign_keys=f"{cls.__name__}.created_by",
               lazy="raise",
               viewonly=True,
           )
   ```
   *If SQLAlchemy rejects the string form at mapper configuration*, try `foreign_keys=lambda: [cls.created_by]`. *If that also fails*, remove `foreign_keys` completely: today every `CreatorMixin` model has exactly one FK to `profile_usr_user`, so SQLAlchemy can infer it. Log which variant worked.
4. **`app/core/models/event_log.py`** — add below `entity_type = relationship(...)`:

   ```python
       changed_by_user = relationship(
           "ProfileUsrUser", foreign_keys=[changed_by], lazy="raise", viewonly=True
       )
   ```
5. **Tests** (specification in section 6): `tests/test_expand_parse.py` and `tests/test_expand_wiring.py` (at this stage the wiring test only checks `configure_mappers()` and the user schema).

**Checks**

```bash
sudo docker logs --tail 40 alpen-api          # no traceback, "Application startup complete"
curl -s localhost:8000/health                  # ok
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python -m unittest discover -s tests -t . -v
sudo docker exec -w /app alpen-api python tests/baseline_snapshot.py --compare
```

**Done when:** the API restarts without error, all unit tests pass, and `--compare` reports every file `IDENTICAL` (adding relationships and a property must not change any response).

### E2 — Event log pilot

**Edits**

1. **`app/core/schemas/event_log.py`** — add the import `from app.core.utils.expand import ExpandedUser, Link` and:

   ```python
   class CompareEntryRef(BaseModel):
       # existing fields unchanged ...
       changed_by_user: ExpandedUser | None = None          # NEW


   class EventLogDetail(EventLogRead):
       # Single-entry view. Links are returned as IDs only unless ?expand= asks.
       entity_type: EntityTypeRead | None = Link()          # was required in EventLogRead
       changed_by_user: ExpandedUser | None = Link("changed_by")


   class EventLogCompare(BaseModel):
       entity_type: EntityTypeRead | None = None            # was required; now only with ?expand=entity_type
       # other fields unchanged ...
   ```
   Do not modify `EventLogRead`; the list route keeps using it.
2. **`app/core/routes/event_log.py`** — imports: add `from app.core.utils.expand import ExpandPlan, expand_plan` and `EventLogDetail` to the schema import. Keep `joinedload` (the list route uses it). Replace the two routes:

   ```python
   @router.get("/{log_id}", response_model=ApiResponse[EventLogDetail])
   async def get_event_log(
       log_id: UUID,
       _user: ProfileUsrUser = Depends(require_groups("administrator")),
       plan: ExpandPlan = Depends(expand_plan(EventLogDetail)),
       db: AsyncSession = Depends(get_db),
   ):
       stmt = (
           select(CoreLogEvent)
           .options(*plan.load_options(CoreLogEvent))
           .where(CoreLogEvent.id == log_id)
       )
       result = await db.execute(stmt)
       entry = result.scalar_one_or_none()
       if entry is None:
           raise AppError(404, "Not found", error_message="Event log entry not found.")
       return ok(plan.render(entry))
   ```

   For `compare_event_logs`: add the parameter `plan: ExpandPlan = Depends(expand_plan(EventLogDetail))` **after** `_user` and before `db`; in the first query replace `.options(joinedload(CoreLogEvent.entity_type))` by `.options(*plan.load_options(CoreLogEvent))`; keep `.unique()`. Everything up to `older, newer = ...`, the `rows` query and the `net` / `warnings` / `changes` loop stay exactly as they are. Then replace only the tail, starting at the old `def ref(e):`:

   ```python
       older_d, newer_d = plan.render(older), plan.render(newer)   # render each entry once

       def ref(d):
           return {
               "id": d["id"], "seq": d["seq"], "action": d["action"],
               "changed_by": d["changed_by"], "changed_at": d["changed_at"],
               "request_id": d["request_id"],
               "changed_by_user": d["changed_by_user"],
           }

       return ok({
           "entity_type": older_d["entity_type"],   # None unless ?expand=entity_type
           "entity_id": older.entity_id,
           "older": ref(older_d),
           "newer": ref(newer_d),
           "events_between": len(rows) - 1,
           "changes": changes,
           "warnings": warnings,
       })
   ```
   Remove the now-unused `et = older.entity_type` block. The `expand` names for compare are the ones of `EventLogDetail` (`entity_type`, `changed_by`) and apply to **both** entries.

   **Parameter order rule for every route in this plan:** declare `plan` *after* the auth dependency (`_user` or `access`). FastAPI resolves dependencies in signature order, so an unauthenticated caller then gets 401/403 before any 400 about `expand`.
3. **Smoke script, part A.** Create `tests/smoke_expand.py` (stdlib only, same login and token handling as the baseline script, prints `PASS`/`FAIL`/`SKIP` per check, exit code 1 on any failure) with the event-log scenarios from section 6.3 (A0 to A9).

**Checks**

```bash
sudo docker logs --tail 40 alpen-api
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python -m unittest discover -s tests -t . -v
sudo docker exec -w /app alpen-api python tests/smoke_expand.py
sudo docker exec -w /app alpen-api python tests/baseline_snapshot.py --compare     # all IDENTICAL (event log is not in the baseline)
```

Manual look (needs at least one log row; create one with any POST if the table is empty). The token lives 5 minutes, so run the block quickly or log in again on a 401 (rule 10):

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@alpenwege.dev","password":"!Password@5005"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["response_data"]["access_token"])')
LOG=$(curl -s "localhost:8000/api/v1/event-log?limit=1" -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["response_data"][0]["id"])')
curl -s "localhost:8000/api/v1/event-log/$LOG" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s "localhost:8000/api/v1/event-log/$LOG?expand=changed_by,entity_type" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -s "localhost:8000/api/v1/event-log/$LOG?expand=nope" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: first call has `changed_by_user: null` and `entity_type: null`; second has both filled (`entity_type.key` is the table name, `changed_by_user.username` is set, no password fields); third is 400 with `Allowed at this level: changed_by, entity_type`.

**Done when:** all checks pass. **Stop and report.** This milestone proves the helper end to end (parse, load, render, validation, error format) on the smallest case.

### E3 — Detail schemas for everything else, missing relationships, full wiring test (no behaviour change)

No route is changed in this milestone, so no response changes. Everything added is additive.

**Edits (schemas).** In every file add `from app.core.utils.expand import ExpandedUser, Link` (and the other imports shown). Keep each `*Detail` class directly under its `*Read` class.

`app/core/schemas/ref.py` (put `DifficultySportDetail` after `DifficultySportRead`):

```python
class RefBaseDetail(RefBaseRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class RefWithFactorDetail(RefWithFactorRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class DifficultySportDetail(DifficultySportRead):
    sport_type: RefWithFactorDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
```

`app/compendium/schemas/country.py`:

```python
class CountryDetail(CountryRead):
    created_by_user: ExpandedUser | None = Link("created_by")
```

`app/compendium/schemas/region.py` (import `RefWithFactorDetail` next to `RefWithFactorRead`, and `CountryDetail` next to `CountrySlimRead`):

```python
class RegionDetail(RegionRead):
    country: CountryDetail | None = Link()
    region_type: RefWithFactorDetail | None = Link()
    parent: "RegionDetail | None" = Link()          # self reference, hence the quotes
    created_by_user: ExpandedUser | None = Link("created_by")
```

`app/compendium/schemas/poi.py` (import `RefWithFactorDetail`, `RegionDetail`):

```python
class PoiDetail(PoiRead):
    compendium_type: RefWithFactorDetail | None = Link()
    main_region: RegionDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
```

`app/compendium/schemas/card.py` (import `RefWithFactorDetail`, `PoiDetail`):

```python
class CardDetail(CardRead):
    rarity: RefWithFactorDetail | None = Link()
    compendium_type: RefWithFactorDetail | None = Link()
    poi: PoiDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
```

`app/compendium/schemas/post.py` (import `RefWithFactorDetail`):

```python
class PostDetail(PostRead):
    post_type: RefWithFactorDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
```

`app/compendium/schemas/poi_region.py` (import `PoiDetail`, `RegionDetail`):

```python
class PoiRegionDetail(PoiRegionRead):
    poi: PoiDetail | None = Link()
    region: RegionDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
```

`app/explorer/schemas/gear.py` (import `RefBaseDetail`; `UUID` is already imported):

```python
class GearDetail(GearRead):
    created_by: UUID                       # GearRead does not expose it; Detail does, so the ID is visible next to created_by_user
    company: RefBaseDetail | None = Link()
    gear_type: RefBaseDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
```

If the wiring test reports an unresolved forward reference for `RegionDetail`, add `RegionDetail.model_rebuild()` on the line after the class.

**Edits (models, read-only relationships; add `relationship` to the `sqlalchemy.orm` import where missing).**

- `app/explorer/models/models_agg/gear.py`, at the end of the class:
  ```python
      company = relationship(
          "CoreRefCompany", foreign_keys=[company_id], lazy="raise", viewonly=True
      )
      gear_type = relationship(
          "CoreRefGearType", foreign_keys=[gear_type_id], lazy="raise", viewonly=True
      )
  ```
- `app/core/models/models_ref/core_ref_difficulty_sport.py`, at the end of the class:
  ```python
      sport_type = relationship(
          "CoreRefSportType", foreign_keys=[sport_type_id], lazy="raise", viewonly=True
      )
  ```

`viewonly=True` keeps these links read-only (they are never assigned, and SQLAlchemy will not treat them as part of a save). The older relationships in the repo are not `viewonly`; leave them alone.

**Tests.** Complete `tests/test_expand_wiring.py` with the full table from section 6.2.

**Checks**

```bash
sudo docker logs --tail 40 alpen-api
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python -m unittest discover -s tests -t . -v
sudo docker exec -w /app alpen-api python tests/baseline_snapshot.py --compare      # all IDENTICAL
curl -s localhost:8000/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['paths']), len(d['components']['schemas']))"
```

**Done when:** tests pass, every baseline file is `IDENTICAL`, the number of OpenAPI paths equals the E0 number, and the number of OpenAPI schemas differs from E0 only because of E2 (new: `EventLogDetail`, its envelope, the user schema it uses; gone: the single-entry envelope of `EventLogRead`, which only the old event-log GET used; `EventLogRead` itself stays for the list). Record the numbers. E3 itself adds no schema to OpenAPI, because no route uses the new classes yet.

### E4 — POI pilot (first compendium route; exercises nesting, branching and limits)

**Edits — `app/compendium/routes/poi.py`**

Imports: add `from app.core.utils.expand import ExpandPlan, expand_plan`, and `PoiDetail` to the `app.compendium.schemas.poi` import. **Keep `_EAGER`** (list, POST and PATCH still use it). Replace only `get_poi`:

```python
@router.get("/{poi_id}", response_model=ApiResponse[PoiDetail])
async def get_poi(
    poi_id: UUID,
    access: AccessContext = Depends(resource_access("poi", "read")),
    plan: ExpandPlan = Depends(expand_plan(PoiDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == poi_id)
        .options(*plan.load_options(CompendiumCatPoi))
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="POI not found")
    return ok(plan.render(obj))
```

**Smoke script, part B** — scenarios B1 to B9 from section 6.3.

**Checks**

```bash
sudo docker logs --tail 40 alpen-api
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python -m unittest discover -s tests -t . -v
sudo docker exec -w /app alpen-api python tests/smoke_expand.py
sudo docker exec -w /app alpen-api python tests/baseline_snapshot.py --compare
```

In `--compare`, `pois.list.json` must be `IDENTICAL` and every other baseline file must still be `IDENTICAL` (their routes are not changed yet). `pois.single.json` must be `DIFFERENT` **only** in the allowed way: `compendium_type` and `main_region` went from objects to `null`, and `created_by_user` appeared.

**Done when:** all checks pass. **Stop and report.** After this, only mechanical roll-out remains.

### E5 — Remaining single GET routes

For each route below change **only** the single GET. The rest of the file stays as it is.

**In every file** add `from app.core.utils.expand import ExpandPlan, expand_plan` and add the `*Detail` class from the table below to the file's existing import from its schema module (for example `from app.compendium.schemas.region import RegionCreate, RegionDetail, RegionRead, RegionUpdate`). Declare the new `plan` parameter **after** the `access` parameter and before `db`, exactly as in the POI route in E4.

**Pattern A — routes that already use `_EAGER` in their single GET** (`region.py`, `card.py`, `post.py`, `poi_region.py`): add the `plan` dependency, replace `.options(*_EAGER)` by `.options(*plan.load_options(Model))` in the single GET only, change `response_model` to `ApiResponse[XDetail]`, return `ok(plan.render(obj))`. Keep the `_EAGER` constant.

**Pattern B — routes that use `db.get(...)` today** (`country.py`, `gear.py`, and the ref factory): replace `obj = await db.get(Model, id)` by

```python
    stmt = (
        select(Model)
        .where(Model.id == the_id)
        .options(*plan.load_options(Model))
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
```

Use `select(...)` and not `db.get(..., options=...)`: `get` may return an object already in the session without applying the options. `select` is already imported in all three files. In `gear.py` the variable is called `gear`, not `obj`: keep that name (`gear = (await db.execute(stmt)).scalar_one_or_none()`, `check_object_access(access, gear, ...)`, `return ok(plan.render(gear))`).

| File | Function | Response schema | Model |
|---|---|---|---|
| `app/compendium/routes/region.py` | `get_region` | `RegionDetail` | `CompendiumCatRegion` |
| `app/compendium/routes/country.py` | `get_country` | `CountryDetail` | `CompendiumCatCountry` |
| `app/compendium/routes/card.py` | `get_card` | `CardDetail` | `CompendiumCatCard` |
| `app/compendium/routes/post.py` | `get_post` | `PostDetail` | `CompendiumCatPost` |
| `app/compendium/routes/poi_region.py` | `get_poi_region` | `PoiRegionDetail` | `CompendiumM2mPoiRegion` |
| `app/explorer/routes/gear.py` | `get_gear` | `GearDetail` | `ExplorerAggGear` |

**Ref factory** (`app/core/routes/ref.py`): add the parameter `detail_schema` to `_build_ref_router(...)`, change only `get_item`:

```python
    @router.get("/{item_id}", response_model=ApiResponse[detail_schema])
    async def get_item(
        item_id: UUID,
        access: AccessContext = Depends(resource_access(resource_key, "read")),
        plan: ExpandPlan = Depends(expand_plan(detail_schema)),
        db: AsyncSession = Depends(get_db),
    ):
        stmt = (
            select(model)
            .where(model.id == item_id)
            .options(*plan.load_options(model))
        )
        obj = (await db.execute(stmt)).scalar_one_or_none()
        check_object_access(access, obj, not_found_msg=f"{slug} not found")
        return ok(plan.render(obj))
```

and pass `detail_schema=` at the four call sites: `RefBaseDetail` (companies, gear-types), `RefWithFactorDetail` (the 15 factor tables and sport-types), `DifficultySportDetail` (difficulty-sports). Add the three `*Detail` names to the `app.core.schemas.ref` import and `ExpandPlan, expand_plan` to the imports.

**Smoke script, part C** — scenarios C1 to C8 from section 6.3. C5 (shared-row case) is the important one.

**Checks:** the same four commands as in E4.

**Done when:** all pass, and `--compare` shows every `*.list.json` as `IDENTICAL` and every `*.single.json` as `DIFFERENT` **only** in the allowed way (every Detail schema adds `created_by_user`, so none of the singles stays `IDENTICAL`; a country, for example, differs only by that new key). **Stop and report.**

### E6 — Docs, OpenAPI, regression, query count, cleanup

1. **README.** Apply Appendix B.
2. **OpenAPI.** Open `http://localhost:8000/docs` (or fetch `/openapi.json`): `GET /api/v1/pois/{poi_id}` shows a query parameter `expand` with the description produced by `expand_plan` and the response schema `ApiResponse_PoiDetail_`. `GET /api/v1/pois` (list) still shows `PoiRead`. Confirm the page loads without errors (recursive schemas such as `RegionDetail` must render).
3. **Full regression:** unit tests, `smoke_expand.py`, `baseline_snapshot.py --compare` (E5 command set).
4. **Query count** (no code change; uses the Postgres log):
   ```bash
   sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "ALTER SYSTEM SET log_statement='all'" -c "SELECT pg_reload_conf()"
   # For each request below: count "execute" lines, send the request, count again, take the difference.
   sudo docker logs alpen-postgres 2>&1 | grep -c "execute "
   ```
   Requests (use one POI id; the same auth cost is included in every number, so compare the *differences*): `GET /pois/{id}`; `…?expand=compendium_type,main_region`; `…?expand=created_by`; `…?expand=main_region.country,main_region.region_type,compendium_type,created_by`.
   Expected: the default request is **two statements fewer** than before this work (before: POI + type + region selects; now: POI only). `expand=compendium_type,main_region` equals the old count. `expand=created_by` adds two statements (the user and the user's credentials, which are loaded together), or none if the creator is the caller himself, because that user is already in the session from authentication. Each additional link adds one statement. Write the real numbers into the log. Then undo:
   ```bash
   sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "ALTER SYSTEM RESET log_statement" -c "SELECT pg_reload_conf()"
   ```
5. **Cleanup.** Delete `tests/_baseline/` (`sudo rm -rf tests/_baseline`, because the container created it as root). Keep `tests/` (unit tests and smoke script). Make sure nothing temporary is left (no `echo=True`, no debug prints). The smoke script leaves a few permanent rows in the event log (created, updated, deleted for its test country); that is expected.
6. **Final report to the user** (short, plain English): what changed, the checks that passed, the real query counts, anything that deviated from this plan, and a reminder of the known visibility consequence (section 3, item 9).

**Done when:** the user confirms.

---

## 5. What every single-object GET accepts after the work

"Level 1" are the names allowed directly in `?expand=`. Deeper paths follow the links of the nested object (maximum 3 segments). `created_by` is available on every object that has a `*Detail` schema, so `X.created_by` is a valid deeper path as long as it stays within 3 segments.

| Endpoint | Detail schema | Level 1 names | Useful deeper paths |
|---|---|---|---|
| `GET /event-log/{id}` | `EventLogDetail` | `entity_type`, `changed_by` | none (neither target has links) |
| `GET /event-log/{id_1}/compare/{id_2}` | uses `EventLogDetail` names | `entity_type`, `changed_by` (applies to both entries) | none |
| `GET /pois/{id}` | `PoiDetail` | `compendium_type`, `main_region`, `created_by` | `main_region.country`, `main_region.region_type`, `main_region.parent`, `compendium_type.created_by` |
| `GET /cards/{id}` | `CardDetail` | `rarity`, `compendium_type`, `poi`, `created_by` | `poi.main_region.country`, `poi.compendium_type` |
| `GET /regions/{id}` | `RegionDetail` | `country`, `region_type`, `parent`, `created_by` | `parent.parent.parent`, `country.created_by` |
| `GET /countries/{id}` | `CountryDetail` | `created_by` | none |
| `GET /posts/{id}` | `PostDetail` | `post_type`, `created_by` | `post_type.created_by` |
| `GET /poi-regions/{id}` | `PoiRegionDetail` | `poi`, `region`, `created_by` | `poi.main_region.country`, `region.country`, `region.parent.parent` |
| `GET /gear/{id}` | `GearDetail` | `company`, `gear_type`, `created_by` | `company.created_by` |
| `GET /ref/{slug}/{id}` (18 tables) | `RefBaseDetail` / `RefWithFactorDetail` | `created_by` | none |
| `GET /ref/difficulty-sports/{id}` | `DifficultySportDetail` | `sport_type`, `created_by` | `sport_type.created_by` |

---

## 6. Test plan

All tests use only the standard library (`unittest`, `urllib`). Run unit tests with
`sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python -m unittest discover -s tests -t . -v`
(`-t .` needs the empty `tests/__init__.py`). Unit tests need **no database**.

### 6.1 `tests/test_expand_parse.py` (helper, no database)

Define small schemas in the test file:

```python
class D(BaseModel):
    id: int

class C(BaseModel):
    id: int
    d: D | None = Link()

class B(BaseModel):
    id: int
    c: C | None = Link()
    d2: D | None = Link()

class A(BaseModel):
    id: int
    name: str
    b: B | None = Link()
    c: C | None = Link()
    creator: D | None = Link("created_by")

class Wide(BaseModel):          # 11 links named l0 .. l10, each "D | None = Link()"
    ...
```

Cases (use `types.SimpleNamespace` for objects):

1. `None`, `""`, `"  "`, `","` give an empty tree and `load_options` returns `[]`.
2. `"b"` gives one node `b`. `"b.c.d"` is accepted (3 levels).
3. `"b.c.d.x"` raises `AppError` 400 and the message contains "levels".
4. `"b.c,b.d2,c"` merges: `b` exists once with children `c` and `d2`, plus top-level `c` (4 nodes).
5. `"created_by"` works and resolves to attribute `creator`; `"creator"` (the field name) is rejected.
6. `"zzz"` raises 400; the message contains "Allowed at this level" and lists `b, c, created_by`.
7. Scalar fields (`id`, `name`) are rejected.
8. `"b."`, `".b"`, `"a..b"` are rejected.
9. `Wide` with 10 links is accepted; with 11 it raises 400 (limit).
10. `" b , b "` gives one node (whitespace and duplicates).
11. `render` without expand: all scalar fields present, every link field `None`, even though the object carries nested data.
12. `render("b.c")`: `b.c` filled; `b.d2` stays `None` although `obj.b.d2` is populated; top-level `c` is `None`.
13. A requested link whose attribute is `None` renders `None` (no crash).
14. **Lazy-raise simulation:** an object whose link attribute is a property that raises `RuntimeError`. `render` without expand must not raise (proves unrequested links are never read).
15. The `AppError` has `status_code == 400` and `error_errors[0]["field"] == "expand"`.
16. A `Link()` on a non-model type (`x: int | None = Link()`) makes `_links` raise `TypeError` with a helpful message.

### 6.2 `tests/test_expand_wiring.py` (schemas against models, no database)

Import every model package exactly like `create_tables()` does (`app.core.models`, `app.assets.models`, `app.compendium.models`, `app.explorer.models`, `app.profile.models`, `app.social.models`) and every schema module that defines a `*Detail`. Table:

```python
PAIRS = {
    EventLogDetail: CoreLogEvent,
    PoiDetail: CompendiumCatPoi,
    CardDetail: CompendiumCatCard,
    RegionDetail: CompendiumCatRegion,
    CountryDetail: CompendiumCatCountry,
    PostDetail: CompendiumCatPost,
    PoiRegionDetail: CompendiumM2mPoiRegion,
    GearDetail: ExplorerAggGear,
    RefBaseDetail: CoreRefCompany,
    RefWithFactorDetail: CoreRefRarity,
    DifficultySportDetail: CoreRefDifficultySport,
    EntityTypeRead: CoreRefEntityType,
    UserRead: ProfileUsrUser,
}
```

Assertions:

- **W1** `sqlalchemy.orm.configure_mappers()` does not raise.
- **W2** For every pair, every non-link field of the schema exists on the model class (`hasattr`). This catches schema and model drift, and checks `user_group` on `ProfileUsrUser`.
- **W3** For every link: the attribute is in `sa_inspect(model).relationships`; the relationship target equals the model that `PAIRS` maps to the link's target schema, except for the two shared ref schemas, where the target must be a `CoreRef*` model (subclass of `ReferenceBaseMixin`).
- **W4** Every link target schema is itself a key of `PAIRS`.
- **W5** Every class named `*Detail` found in the imported schema modules is a key of `PAIRS` (forces new Detail classes into this table).
- **W6** No field name containing `password`, `hash`, `credentials` or `token` exists in any schema reachable through links (including `UserRead`). Walk the links with a visited set, because `RegionDetail.parent` points back to `RegionDetail`.
- **W7** `ProfileUsrUser.user_group.fget(SimpleNamespace(credentials=SimpleNamespace(user_group="editor")))` returns `"editor"`; with `credentials=None` it returns `None`.
- **W8** Every mapped class that subclasses `CreatorMixin` has `created_by_user` with `lazy == "raise"` and `viewonly` true.

### 6.3 `tests/smoke_expand.py` (live API, needs the seeded users)

Users: `admin@alpenwege.dev`, `guest@alpenwege.dev` (also `editor@`), password `!Password@5005`. Helpers `login`, `call(method, path, token, body)`; keep one token per user and handle rotation as in rule 10 (adopt `X-Access-Token`, log in again once on 401). Each check prints `PASS`, `FAIL` or `SKIP (reason)`; the script ends with a summary and exits 1 if anything failed. Anything it creates, it deletes in a `finally`; the event log keeps the resulting `created` / `updated` / `deleted` rows, which is expected. **Error texts live in `response_details.error_message`** (`response_message` is only "Bad request"), so every check on a 400 message reads that field.

**Part A, event log (added in E2)**

- A0 Setup as admin: `POST /countries` (`name "ZZ Expand Test"`, `iso_code "ZZ"`, a point location, `capital "Old"`), then `GET /event-log?entity_id=<country id>&limit=5` and take the `created` entry.
- A1 Default `GET /event-log/{id}`: `changed_by` is a UUID, `changed_by_user` and `entity_type` are `null`, `entity_type_id` is set.
- A2 `?expand=changed_by`: `changed_by_user.id == changed_by`, has `username`, `email`, `user_group == "administrator"`; the response text contains neither `password` nor `hash`.
- A3 `?expand=entity_type`: `entity_type.key == "compendium_cat_country"` and `changed_by_user` is `null`.
- A4 `?expand=changed_by,entity_type`: both set.
- A5 `?expand=nope`: status 400, `response_status` false, `response_details.error_message` contains `changed_by` and `entity_type`, `response_details.error_errors[0].field == "expand"`.
- A6 `?expand=changed_by.x`: 400 (a user has no links).
- A7 Compare: `PATCH /countries/{id}` with `{"capital": "New"}` creates a second entry. Without expand, `entity_type` is `null` and `older.changed_by_user` is `null`. With `?expand=changed_by,entity_type`, both entries have `changed_by_user` and `entity_type.key` is set; `changes.capital` is still `{"from": "Old", "to": "New"}`.
- A8 Guest token on `GET /event-log/{id}?expand=changed_by`: 403.
- A9 Cleanup: `DELETE /countries/{id}`.

**Part B, POI (added in E4)**

- B1 `GET /pois?limit=1` gives a POI id (skip the part if there is none).
- B2 Default `GET /pois/{id}`: `compendium_type_id` set, `compendium_type`, `main_region`, `created_by_user` all `null`, `location` is a GeoJSON point (geometry still works).
- B3 `?expand=compendium_type`: object with `point_factor`; `created_by_user` still `null`.
- B4 `?expand=main_region.country,main_region.region_type,created_by`: `main_region.country.iso_code` set, `main_region.region_type` set, `main_region.parent` is `null` (not requested), `main_region.created_by_user` is `null`, `created_by_user.username` set.
- B5 `?expand=main_region.parent.parent.country` (4 segments): 400, `error_message` contains "levels". And `?expand=main_region.country.created_by` (3 segments): 200, with `main_region.country.created_by_user` filled.
- B6 `?expand=main_region.nope`: 400, `error_message` lists `country, created_by, parent, region_type`.
- B7 As guest, `?expand=created_by`: 200 and `created_by_user.email` is a string. (This documents the accepted visibility rule. If the rule is ever narrowed, change this check on purpose.)
- B8 Lists unchanged: `GET /pois?limit=2` items still have non-null `compendium_type` and `main_region`.
- B9 Random UUID: 404 without expand; 400 with `?expand=nope` (the parameter is checked first).

**Part C, the rest (added in E5)**

- C1 Regions: `?expand=country,region_type,parent,created_by` works; `parent.parent.parent` is accepted (200); `parent.parent.parent.parent` is 400.
- C2 Countries: `?expand=created_by` works; `?expand=zzz` is 400 and lists `created_by`.
- C3 Ref: `GET /ref/rarities/{id}`: default `created_by_user` is `null`; `?expand=created_by` fills it. For `/ref/difficulty-sports`, if a row has a `sport_type_id`: `?expand=sport_type` returns an object (skip if none).
- C4 Gear (as admin): create with the first company and gear type from `/ref/companies` and `/ref/gear-types` (skip if empty). Default: `company` and `gear_type` are `null`, `created_by` is set. `?expand=company,gear_type,created_by` fills all three. Delete the gear.
- C5 **Shared row (the important one).** Create a POI-region link with `POST /poi-regions` using a POI id, that POI's own `main_region_id` as `region_id`, and `slot_position` 99. Then:
  `?expand=poi.main_region,region.country` must give `region.country` as an object (**not null**) and `poi.main_region.country` as `null`;
  `?expand=region,poi.main_region.country` must give the opposite.
  Both responses concern the same database row, which is exactly the case that breaks a `noload` design. Delete the link afterwards.
- C6 Cards and posts: if the collection is empty print `SKIP (no rows)`; otherwise cards `?expand=poi.main_region.country` and posts `?expand=post_type,created_by`.
- C7 Every single GET also accepts an empty `?expand=` and returns the same body as without it (ignore `response_request_id` when comparing).
- C8 No response collected during the run contains the text `password`.

---

## 7. Risks and rollback

| # | Risk | How it shows up | Mitigation |
|---|---|---|---|
| R1 | The `created_by_user` relationship breaks mapper configuration for one of the 45 mapped classes | API does not start; W1 and W8 fail | Three variants for `foreign_keys` in E1; rollback by deleting the attribute from `CreatorMixin` |
| R2 | pydantic, FastAPI or SQLAlchemy version differs from what the code assumes (`model_fields[...].json_schema_extra`, annotation resolution, `Load.options`). Versions are unpinned; at review time a fresh install resolved to about FastAPI 0.157, pydantic 2.14, SQLAlchemy 2.1, and the reference code was checked against the documentation of those lines | unit tests fail in E1 | E0 records the real versions; do not rebuild images meanwhile (rule 11); fallback: keep link metadata in a class-level dict next to each Detail schema |
| R3 | Recursive `RegionDetail` breaks OpenAPI or `/docs` | `/openapi.json` fails in E3/E4 | Fallback: a non-recursive `RegionParentDetail` without `parent`. Tell the user that `parent.parent` is then not possible |
| R4 | Schema and model drift: `render` asks for an attribute the model lacks | W2 fails; at runtime a 500 | W2 and W5 run in every milestone |
| R5 | Too many queries | query count in E6 | Each requested link costs one SELECT; at most 10 links per request |
| R6 | Clients of the single GETs lose their nested objects | client errors outside this repo | Announce it; lists are unaffected; the README explains `?expand=` |
| R7 | Privacy: any reader of an object can expand its creator's full profile (email, birth date, heart rates). For compendium and ref data the creators are admins and editors; for public gear (and later tracks and trips) they are ordinary users | seen in smoke test B7 | Accepted by the user. One-line switch: change `ExpandedUser = UserRead` in `expand.py` to a slim schema (id and username), or to a function that depends on the caller. Recommended to be revisited before tracks and trips get Detail schemas |
| R8 | OneDrive sync saves a half-written file and `--reload` crashes | traceback in `docker logs` | Wait for the sync, then check the logs again |

**Rollback.** There is no database change, so rollback is file-only: copy `../app_before_expand/.` back over `app/` (and `README.before_expand.md` over `README.md`), then `sudo docker restart alpen-api`. Per milestone, undo the route edits first, then the Detail schemas, then the relationships.

---

## 8. Recipe for future single-object GETs (tracks, trips, ...)

1. **Model.** Add a read-only `relationship(..., foreign_keys=[...], lazy="raise", viewonly=True)` for every FK that should be expandable. The user link (`created_by_user`) is already there for models with `CreatorMixin`.
2. **Schema.** `class XDetail(XRead)` with `link: YDetail | None = Link()`. The nested type must itself be a Detail schema, otherwise deeper paths and `created_by` are not available.
3. **Route.** `plan: ExpandPlan = Depends(expand_plan(XDetail))`, `select(Model).where(...).options(*plan.load_options(Model))`, `return ok(plan.render(obj))`, `response_model=ApiResponse[XDetail]`.
4. **Tests.** Add `XDetail: Model` to `PAIRS` in `tests/test_expand_wiring.py` and one scenario to the smoke script.
5. **Never read an unrequested link from the ORM object yourself.** `render` is the only place that touches links.

---

## 9. Defaults chosen by the planner (the user may veto any of them)

1. Unrequested links appear with the value `null` (alternative: leave the key out).
2. `GearDetail` also returns `created_by` (the current `GearRead` does not).
3. The compare endpoint supports `expand` (`entity_type`, `changed_by`), and its `entity_type` is now `null` unless requested.
4. A bad `expand` gives 400, not 422 and not "ignore silently".
5. Lists, POST and PATCH keep their current shape, so a list item still contains nested objects while the single GET does not. This difference is intentional.
6. The `sport_type` link on difficulty-sports is included.
7. The full user profile is visible to every reader who can read the object (the user's rule). With the seeded policies that includes guests, and for public gear it includes the profile of ordinary users.
8. Tests live in `tests/`, use only the standard library, and add no dependency.

---

## 10. Order of work relative to the other plans in this folder

1. **`api_routes_structure_proposal.md`** (proposal, not yet approved) moves route files: `core/routes/ref.py` becomes a `ref/` package with `_factory.py`, `profile/routes/me.py` and `admin.py` move into `user/`, and so on. Its check is "`openapi.json` before and after must be identical". This plan **deliberately changes** the OpenAPI response schemas of the single GETs. So do not interleave the two:
   - Recommended order: finish E0 to E6 first. Then take a fresh `openapi_before.json` and start the structure work. The route moves are pure moves, so the `plan` / `detail_schema` edits travel with the code (`_build_ref_router` moves to `ref/_factory.py` and its call sites into the per-table files).
   - If the structure work is done first: translate the file paths in E5 (`app/core/routes/ref.py::_build_ref_router` becomes `app/core/routes/ref/_factory.py`, and the four call sites live in the per-table files) and re-record the baseline in E0.
2. **`track_pipeline_implementation_plan.md`**, milestone M3, adds compendium-type schemas and a special router in `app/core/schemas/ref.py` and `app/core/routes/ref.py`. If M3 runs after this plan, the special router must pass `detail_schema=` too (a `CompendiumTypeDetail(CompendiumTypeRead)` with `created_by_user: ExpandedUser | None = Link("created_by")`), and the pair must be added to `PAIRS` in the wiring test. If M3 runs before, E3 and E5 must use the new compendium-type read schema instead of `RefWithFactorRead` for that router.
3. **Future track and trip GET routes** follow section 8. Their creators are ordinary users, so decide the `ExpandedUser` visibility question (risk R7) before those routes are built.

---

## Appendix A — reference implementation: `app/core/utils/expand.py`

Unexecuted. Adjust only if a test shows a real problem, and note the change in the execution log.

```python
# Standard library
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, get_args

# Third-party
from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import selectinload

# Local application
from app.core.utils.responses import AppError
from app.profile.schemas.user_read import UserRead

# The object returned for created_by / changed_by. One alias, so the visibility
# rule can be changed in a single place (for example to a slim schema that has
# only id and username).
ExpandedUser = UserRead

MAX_DEPTH = 3    # longest dotted path, e.g. poi.main_region.country
MAX_LINKS = 10   # distinct links in one request; shared parents count once


def Link(expand_name: str | None = None) -> Any:
    # Mark a field of a *Detail schema as an expandable link.
    # The field must be typed "<DetailSchema> | None". It stays None unless the
    # caller asks for it with ?expand=<name>. expand_name is the public name
    # when it differs from the field name (created_by_user -> "created_by").
    extra: dict[str, Any] = {"x-expand": True}
    if expand_name:
        extra["x-expand-name"] = expand_name
    return Field(default=None, json_schema_extra=extra)


@dataclass(frozen=True)
class _LinkInfo:
    attr: str                 # field name in the schema == attribute name on the ORM object
    public: str               # name accepted in ?expand=
    target: type[BaseModel]   # schema of the linked object


def _target_schema(schema, name, annotation) -> type[BaseModel]:
    for arg in get_args(annotation) or (annotation,):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return arg
    raise TypeError(
        f"{schema.__name__}.{name} is marked Link() but its type {annotation!r} "
        f"is not a pydantic model (unresolved forward reference? "
        f"call {schema.__name__}.model_rebuild())."
    )


@lru_cache(maxsize=None)
def _links(schema: type[BaseModel]) -> dict[str, _LinkInfo]:
    # public name -> link info, for every Link() field of the schema.
    found: dict[str, _LinkInfo] = {}
    for name, info in schema.model_fields.items():
        extra = info.json_schema_extra
        if not isinstance(extra, dict) or not extra.get("x-expand"):
            continue
        public = extra.get("x-expand-name") or name
        found[public] = _LinkInfo(
            name, public, _target_schema(schema, name, info.annotation)
        )
    return found


@dataclass
class _Node:
    link: _LinkInfo
    children: dict[str, "_Node"] = field(default_factory=dict)


def _bad(message: str) -> AppError:
    return AppError(
        400,
        "Bad request",
        error_message=message,
        error_errors=[
            {"field": "expand", "code": "invalid_expand", "message": message}
        ],
    )


def _count(tree: dict[str, _Node]) -> int:
    return sum(1 + _count(node.children) for node in tree.values())


def _option(model: type, node: _Node):
    # selectinload for one link; its sub-links become nested options.
    option = selectinload(getattr(model, node.link.attr))
    if node.children:
        child_model = sa_inspect(model).relationships[node.link.attr].mapper.class_
        option = option.options(
            *[_option(child_model, child) for child in node.children.values()]
        )
    return option


def _render(schema: type[BaseModel], obj: Any, tree: dict[str, _Node]) -> dict[str, Any]:
    # Plain dict of the schema's fields. Only requested links are read from the
    # object, so unrequested (lazy="raise") relationships are never touched.
    by_attr = {info.attr: info for info in _links(schema).values()}
    out: dict[str, Any] = {}
    for name in schema.model_fields:
        info = by_attr.get(name)
        if info is None:
            out[name] = getattr(obj, name)
            continue
        node = tree.get(info.public)
        child = getattr(obj, name) if node is not None else None
        out[name] = None if child is None else _render(info.target, child, node.children)
    return out


@dataclass
class ExpandPlan:
    schema: type[BaseModel]
    tree: dict[str, _Node]

    @classmethod
    def parse(cls, schema: type[BaseModel], expand: str | None) -> "ExpandPlan":
        # Validate ?expand= against the schema and build the tree of links.
        # Raises AppError 400 for unknown names, paths deeper than MAX_DEPTH
        # and more than MAX_LINKS distinct links.
        tree: dict[str, _Node] = {}
        for raw in (expand or "").split(","):
            path = raw.strip()
            if not path:
                continue
            parts = [p.strip() for p in path.split(".")]
            if len(parts) > MAX_DEPTH:
                raise _bad(
                    f"'{path}' is {len(parts)} levels deep; the maximum is {MAX_DEPTH}."
                )
            level, current = tree, schema
            for part in parts:
                links = _links(current)
                link = links.get(part)
                if link is None:
                    allowed = ", ".join(sorted(links)) or "(nothing)"
                    raise _bad(
                        f"Cannot expand '{part}' in '{path}'. "
                        f"Allowed at this level: {allowed}."
                    )
                node = level.setdefault(part, _Node(link))
                level, current = node.children, link.target
        total = _count(tree)
        if total > MAX_LINKS:
            raise _bad(f"{total} links requested; the maximum is {MAX_LINKS}.")
        return cls(schema, tree)

    def load_options(self, model: type) -> list:
        # selectinload options for select(model).options(*...): one extra
        # SELECT per requested link.
        return [_option(model, node) for node in self.tree.values()]

    def render(self, obj: Any) -> dict[str, Any]:
        # ORM object -> dict for the response_model. Unrequested links are None.
        return _render(self.schema, obj, self.tree)


def expand_plan(schema: type[BaseModel]):
    # FastAPI dependency factory: Depends(expand_plan(PoiDetail)) adds the
    # documented ?expand= query parameter and returns the parsed ExpandPlan.
    names = ", ".join(sorted(_links(schema))) or "none"
    description = (
        "Comma-separated links to return as full objects instead of only their "
        f"IDs. Allowed: {names}. Nest with dots, up to {MAX_DEPTH} levels "
        f"(for example a.b.c). At most {MAX_LINKS} links per request."
    )

    async def _dependency(
        expand: str | None = Query(None, description=description),
    ) -> ExpandPlan:
        return ExpandPlan.parse(schema, expand)

    return _dependency
```

---

## Appendix B — README changes (done in E6)

1. In section "Compendium (catalog)", replace the sentence "GET endpoints return nested objects one level deep (FK IDs are accepted on create/update; full sub-objects come back on read)." with: "List endpoints return their nested objects one level deep. Single-object GET endpoints return IDs only; add `?expand=` to get the full objects (see below)."
2. Replace the sentence "The GET response returns the full nested objects:" with "`GET /regions/{id}?expand=country,region_type` returns the nested objects:". The JSON example stays as it is.
3. Add this section directly after the Compendium section:

````markdown
### Expanding linked objects (`?expand=`)

Single-object GET endpoints (`/pois/{id}`, `/regions/{id}`, `/cards/{id}`, `/posts/{id}`, `/poi-regions/{id}`, `/countries/{id}`, `/gear/{id}`, `/ref/{slug}/{id}`, `/event-log/{id}`) return linked objects as **IDs only**. Add `expand` with a comma-separated list of links to get the full object instead:

```bash
curl "http://localhost:8000/api/v1/regions/<id>?expand=country,region_type,created_by" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/pois/<id>?expand=main_region.country,compendium_type" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/event-log/<id>?expand=changed_by,entity_type" -H "Authorization: Bearer $TOKEN"
```

- Nest with dots, at most 3 levels per path (`poi.main_region.country`). One request may expand at most 10 links in total.
- The allowed names are listed in the `expand` parameter description of each endpoint in Swagger.
- An unknown name, a path deeper than 3 levels or more than 10 links returns `400`.
- Links that are not requested are returned as `null` next to their ID (`"main_region_id": "…", "main_region": null`). `created_by` and `changed_by` are returned as `created_by_user` and `changed_by_user`.
- If you can read an object, you can see everything expanded inside it, including the full user profile behind `created_by` and `changed_by`.
- List endpoints (`GET /pois`, ...) are unchanged and still contain their nested objects.
````

---

## Execution log (the implementing agent fills this in)

| Date | Milestone | Result | Notes and deviations |
|---|---|---|---|
| | E0 | | |
| | E1 | | |
| | E2 | | |
| | E3 | | |
| | E4 | | |
| | E5 | | |
| | E6 | | |

**E0 data:** library versions: … · OpenAPI paths / schemas before: … · row counts per collection: …
**E1 variant used for `foreign_keys`:** string / lambda / omitted
**E6 query counts:** default POI … · `expand=compendium_type,main_region` … · `expand=created_by` … · four-path request …
