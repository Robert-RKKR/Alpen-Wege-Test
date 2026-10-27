# Executed by apply_filters.py (it provides ROOT, sub_once, stop, GZIP). Adds `compare --lists` to scripts/route_map.py.
REL = "scripts/route_map.py"

sub_once(REL, "    python scripts/route_map.py compare BEFORE.json AFTER.json [--rules RULES.json [--step N]] [--expand]\n",
         "    python scripts/route_map.py compare BEFORE.json AFTER.json [--rules RULES.json [--step N]] [--expand] [--lists]\n")

sub_once(REL, "`probe` sends every HTTP route of the app", '''With --lists a list route (a GET that had the query parameter `limit`) may differ in three ways, and only these: the
parameter list, the dependencies and the classes the function uses. The parameters: every old parameter except limit,
offset and skip is still there with the same type (a description or a pattern may be added, one value may become a list of values); limit and offset (skip on the users list) are there, their default and limits may change;
every new parameter is a query parameter. The dependencies: the login and permission ones must be the same,
the paging, sort and filter ones are ignored. The classes: only UserService, AppError and MgmtRefEntityType may disappear (the filter classes use them now). Everything
else of the route (200 answer, status, tags, summary) must be identical. The middleware list may only gain
GZipMiddleware. The number of list routes that changed is printed. Use it after the filters change
(get_filters_implementation_plan.md).

`probe` sends every HTTP route of the app''')

sub_once(REL, "# compare --expand: a GET route that gained the query parameter ?expand= may differ in these fields\n",
         "# compare --lists: a list route may differ in these fields\nLIST_FIELDS = (\"parameters\", \"permissions\", \"uses\")\nLIST_CLASSES_MAY_GO = (\"UserService\", \"AppError\", \"MgmtRefEntityType\")   # now used inside a filter class\n"
         "# compare --expand: a GET route that gained the query parameter ?expand= may differ in these fields\n")

sub_once(REL, "def compare(before: dict, after: dict, rules: list[dict] | None, step: int | None = None, expand: bool = False) -> list[str]:\n",
         '''def _param_name(param: str) -> str:
    return param.split(":", 2)[1] if param.startswith("query:") else ""


def _loose(param: str):
    # the parameter without the documentation: its place, name, required flag and type; a description, a pattern or
    # a limit may be added
    place, name, required, schema = param.split(":", 3)

    def strip(node):
        if isinstance(node, dict):
            node = {k: strip(v) for k, v in node.items() if k not in ("description", "title", "pattern", "minimum", "maximum", "maxItems", "minLength", "maxLength")}
            if "anyOf" in node:   # one value or a list of them (?sport_type_id=a&sport_type_id=b) is the same parameter
                branches = [b["items"] if b.get("type") == "array" and "items" in b else b for b in node["anyOf"]]
                node["anyOf"] = [b for i, b in enumerate(branches) if b not in branches[:i]]
            return node
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return place, name, required, strip(json.loads(schema))


def _is_list_dependency(call: str) -> bool:
    return "app.core.utils.listing." in call or call.endswith('Filters"}')


def _is_list_route(key: str, record: dict) -> bool:
    return key.startswith("GET ") and any(p.startswith("query:limit:") for p in record.get("parameters", []))


def _list_change_ok(field: str, want, have) -> bool:
    # what a list route may change, field by field
    if field == "parameters":
        kept = [p for p in want if _param_name(p) not in ("limit", "offset", "skip")]
        names = {_param_name(p) for p in have}
        return (all(_loose(p) in [_loose(h) for h in have] for p in kept)
                and "limit" in names and ("offset" in names or "skip" in names)
                and all(p.startswith("query:") for p in have if p not in want))
    if field == "permissions":
        return [p for p in have if not _is_list_dependency(p)] == want   # the paging, sort and filter dependencies are ignored
    if field == "uses":
        return all(name.endswith(LIST_CLASSES_MAY_GO) for name in set(want) - set(have))
    return False


def compare(before: dict, after: dict, rules: list[dict] | None, step: int | None = None, expand: bool = False, lists: bool = False) -> list[str]:
''')

sub_once(REL, "    gained_expand = 0\n    if before.get(\"fastapi_version\")", "    gained_expand = 0\n    changed_lists = 0\n    if before.get(\"fastapi_version\")")

sub_once(REL, '''        for field in COMPARED_FIELDS:
            want = record.get(field)
            if gained and field in EXPAND_FIELDS and _expand_change_ok(field, want, got.get(field)):
                continue
''', '''        listed = lists and _is_list_route(old_key, record)
        changed_lists += 1 if listed and any(record.get(f) != got.get(f) for f in LIST_FIELDS) else 0
        for field in COMPARED_FIELDS:
            want = record.get(field)
            if gained and field in EXPAND_FIELDS and _expand_change_ok(field, want, got.get(field)):
                continue
            if listed and field in LIST_FIELDS and _list_change_ok(field, want, got.get(field)):
                continue
''')

sub_once(REL, '''    for field in ("middleware", "exception_handlers"):
        if field in before and before[field] != after.get(field):
''', '''    for field in ("middleware", "exception_handlers"):
        if lists and field == "middleware" and field in before and after.get(field) is not None:
            gzip_only = [m for m in after[field] if m not in before[field]]
            if [m for m in after[field] if m in before[field]] == before[field] and all(m.endswith("GZipMiddleware") for m in gzip_only):
                continue
        if field in before and before[field] != after.get(field):
''')

sub_once(REL, '''    if expand:
        errors.append(f"NOTE      {gained_expand} route(s) gained the query parameter expand")
''', '''    if expand:
        errors.append(f"NOTE      {gained_expand} route(s) gained the query parameter expand")
    if lists:
        errors.append(f"NOTE      {changed_lists} list route(s) changed their parameters")
''')

sub_once(REL, '''    args = parser.parse_args()

    if args.command == "dump":''', '''    p_cmp.add_argument("--lists", action="store_true", help="allow the changes of the list filters (see the module doc)")
    args = parser.parse_args()

    if args.command == "dump":''')
sub_once(REL, "errors = compare(before, after, rules, args.step, args.expand)", "errors = compare(before, after, rules, args.step, args.expand, args.lists)")
sub_once(REL, "(' except the routes that gained ?expand=' if args.expand else '')}\")",
         "(' except the routes that gained ?expand=' if args.expand else '') + (' except the list routes' if args.lists else '')}\")")
