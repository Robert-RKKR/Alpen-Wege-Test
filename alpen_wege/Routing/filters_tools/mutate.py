import shutil, subprocess, sys, re, os
MUTS = [
 ("M01 before() inclusive", "app/core/utils/listing.py", "return column < value if value is not None else None", "return column <= value if value is not None else None"),
 ("M02 no LIKE escaping", "app/core/utils/listing.py", 'return text.replace("\\\\", "\\\\\\\\").replace("%", "\\\\%").replace("_", "\\\\_")', "return text"),
 ("M03 no tie breaker", "app/core/utils/listing.py", "return stmt.order_by(order, *ties)", "return stmt.order_by(order)"),
 ("M04 nulls not last", "app/core/utils/listing.py", "        if _may_be_null(self.column):\n            order = order.nulls_last()", "        pass"),
 ("M05 no clamp where there is a maximum", "app/core/utils/listing.py", "return Page(min(limit, maximum) if maximum else limit, offset)", "return Page(limit, offset)"),
 ("M06 default page of 1000 lost", "app/core/utils/listing.py", "PAGE_1000 = (1000, None)", "PAGE_1000 = (100, None)"),
 ("M07 near without geography", "app/core/utils/listing.py", "return func.ST_DWithin(func.geography(column), func.geography(point), radius)", "return func.ST_DWithin(column, point, radius)"),
 ("M08 descending flag inverted", "app/core/utils/listing.py", 'return Sort(options[name], value.startswith("-"), tie_breaker)', 'return Sort(options[name], not value.startswith("-"), tie_breaker)'),
 ("M09 poi total ignores filters", "app/compendium/routes/poi/get_many.py", "total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()", "total = (await db.execute(select(func.count()).select_from(M))).scalar()"),
 ("M10 poi altitude_max dropped", "app/compendium/routes/poi/get_many.py", "at_most(M.altitude_m, self.altitude_max),", ""),
 ("M11 poi scope dropped", "app/compendium/routes/poi/get_many.py", "base = filters.apply(apply_scope(select(M), M, access))", "base = filters.apply(select(M))"),
 ("M12 gear scope dropped", "app/explorer/routes/gear/get_many.py", "base = filters.apply(apply_scope(select(M), M, access))", "base = filters.apply(select(M))"),
 ("M13 track inner join", "app/explorer/routes/track/get_many.py", "base = select(M).outerjoin(G, G.id == M.geo_record_id)", "base = select(M).join(G, G.id == M.geo_record_id)"),
 ("M14 track visibility dropped", "app/explorer/routes/track/get_many.py", "base = apply_visibility(base, access, filters.archived)", "pass"),
 ("M15 gear sort weight wrong column", "app/explorer/routes/gear/get_many.py", '"weight_g": M.weight_g}', '"weight_g": M.name}'),
 ("M16 event_log entity_type ignored", "app/management/routes/event_log/get_many.py", "            entity_type_ids,\n", ""),
 ("M17 users group filter dropped", "app/profile/routes/user/get_many.py", "            equals(C.user_group, self.user_group),\n", ""),
 ("M18 users login after paging", "app/profile/routes/user/get_many.py", '    _admin: ProfileUsrUser = Depends(require_groups("administrator")),\n    page: Page = Depends(page_params(offset_alias="skip")),', '    page: Page = Depends(page_params(offset_alias="skip")),\n    _admin: ProfileUsrUser = Depends(require_groups("administrator")),'),
 ("M19 name filters skip name_pl", "app/core/utils/listing.py", "contains(self.q, model.name, model.name_de, model.name_pl)", "contains(self.q, model.name, model.name_de)"),
 ("M20 ref own scope dropped", "app/core/routes/ref/company/get_many.py", '    if access.scope == "own":\n        base = base.where(M.created_by == access.user.id)\n', ""),
 ("M21 jobs active ignored", "app/management/routes/jobs/get_many.py", 'T.status.in_(("queued", "running")) if self.active else None,', "None,"),
 ("M22 access policy scope filter dropped", "app/profile/routes/access_policy/get_many.py", "            equals(M.scope, self.scope),\n", ""),
 ("M23 offset ignored", "app/compendium/routes/region/get_many.py", ".limit(page.limit).offset(page.offset)", ".limit(page.limit)"),
 ("M24 bbox swapped axes", "app/core/utils/listing.py", "func.ST_MakeEnvelope(west, south, east, north, 4326)", "func.ST_MakeEnvelope(south, west, north, east, 4326)"),
 ("M25 users skip renamed offset", "app/profile/routes/user/get_many.py", 'page_params(offset_alias="skip")),   #', 'page_params()),   #'),
 ("M26 poi-region region_id uses poi_id", "app/compendium/routes/m2m/poi_region/get_many.py", "self.region_id = region_id", "self.region_id = poi_id"),
 ("M27 track recorded_from without coalesce", "app/explorer/routes/track/get_many.py", "since(recorded, self.recorded_from),", "since(M.recorded_at, self.recorded_from),"),
 ("M28 region bbox on the centre", "app/compendium/routes/region/get_many.py", "bbox_condition(M.bbox, self.bbox),", "bbox_condition(M.location, self.bbox),"),
 ("M29 access policy tie breaker only id", "app/profile/routes/access_policy/get_many.py", 'sort_params(SORT, "group", (R.key, M.action, M.id))', 'sort_params(SORT, "group", M.id)'),
 ("M30 nulls last on every column", "app/core/utils/listing.py", "        if _may_be_null(self.column):\n            order = order.nulls_last()", "        order = order.nulls_last()"),
 ("M31 empty string is a value", "app/core/utils/listing.py", 'return column == value if value is not None and value != "" else None', "return column == value if value is not None else None"),
 ("M32 NUL not refused", "app/core/utils/listing.py", 'if "\\x00" in name or "\\x00" in value:', "if False:"),
 ("M33 moment unchecked", "app/core/utils/listing.py", "if value is not None and not 1900 <= value.year <= 2200:", "if False:"),
 ("M34 offset unbounded", "app/core/utils/listing.py", "ge=0, le=MAX_OFFSET, alias=offset_alias,", "ge=0, alias=offset_alias,"),
 ("M35 event-log before swapped", "app/management/routes/event_log/get_many.py", "before(M.changed_at, self.changed_to),", "at_most(M.changed_at, self.changed_to),"),
 ("M36 users default order lost", "app/profile/routes/user/get_many.py", 'sort_params(SORT, "-created_at", M.id)', 'sort_params(SORT, "username", M.id)'),
 ("M37 event log gets a cap", "app/management/routes/event_log/get_many.py", "page_params(PAGE_100)", "page_params(PAGE_100_MAX_500)"),
 ("M38 tracks lose their cap", "app/explorer/routes/track/get_many.py", "page_params(PAGE_100_MAX_500)", "page_params(PAGE_100)"),
 ("M39 limit unbounded", "app/core/utils/listing.py", "ge=1, le=MAX_OFFSET,", "ge=1,"),
]
sel = [int(a) for a in sys.argv[1:]] or range(1, len(MUTS)+1)
env = dict(os.environ)
for i in sel:
    name, rel, old, new = MUTS[i-1]
    shutil.rmtree("/tmp/ex/mut", ignore_errors=True)
    shutil.copytree("/tmp/ex/new", "/tmp/ex/mut", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    path = "/tmp/ex/mut/" + rel
    text = open(path).read()
    if text.count(old) != 1:
        print(f"{name}: PATTERN NOT FOUND ({text.count(old)})"); continue
    open(path, "w").write(text.replace(old, new))
    unit = subprocess.run("cd /tmp/ex/mut && /tmp/ex/v/bin/python -m pytest tests -q -x 2>&1 | tail -3", shell=True, capture_output=True, text=True).stdout.strip().splitlines()
    unit_fail = any("failed" in l or "error" in l.lower() for l in unit[-2:])
    first = next((l for l in unit if l.startswith("FAILED")), "")
    live = ""
    if not unit_fail or "--live" in sys.argv:
        pass
    if not unit_fail:
        cmd = ("cd /tmp/ex && bash down.sh; AW_DIR=mut bash up2.sh; source env.sh; cd mut && /tmp/ex/v/bin/python scripts/list_check.py --gpx /tmp/ex/full.gpx 2>&1 | grep -E '^FAIL|passed' | head -4; bash /tmp/ex/down.sh")
        live = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip().replace("\n", " | ")
    print(f"{name}: unit {'CAUGHT ' + first[:90] if unit_fail else 'survived'}" + (f"; live: {live[:300]}" if live else ""), flush=True)
