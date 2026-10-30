#!/usr/bin/env python3
"""Build the Postman collection and environment for the Alpen Wege API.

    curl http://localhost:8000/openapi.json > openapi.json
    python build_postman.py --openapi openapi.json --out .

Writes `Alpen API.postman_collection.json` and `Alpen API local.postman_environment.json` into --out.
The OpenAPI file is only used to check that every route of the API has a request in the collection
(and that no request points at a route that does not exist), so the collection cannot silently drift
from the API. Run the script again after the API changes.

Names of the Postman variables (match them to the ones you already use):
    --scheme http  --host-var hostname  --port-var port  --api-var api_path  --token-var access_token
URL pattern of every request:  {scheme}://{{host-var}}:{{port-var}}/{{api-var}}/<app>/<resource>
The value of the api variable is `api/v1`.

Structure: one folder per app (core, assets, compendium, explorer, profile, management), one folder per
model inside. Every model folder has List, Create, Get one, Update, Delete (and Upload CSV or the special
calls where the API has them). Create calls save the new id in a variable (`country_id`, `poi_id`, ...)
that the following calls of that model and the models that depend on it use.

Asset links (photo and GPX): `assets / photos / Upload photo` saves `photo_id`; every request whose body can
carry a photo field (`main_photo_id`, see ASSET_LINKS) uses `{{photo_id}}`. The build stops when the API gets
a request body with such a field that the collection does not fill (see check_asset_links), so a new photo
relation cannot be forgotten. Sample files for the upload requests: sample_photo.jpg, sample_track.gpx, sample_icon.svg.

Icon links (the same mechanism): `assets / icons / Upload icon` saves `icon_id` (and `icon_key`); the Create and Update bodies of the
20 reference tables, resource types, countries and regions start with `"icon_id": "{{icon_id}}"` (see ASSET_LINKS).
"""
import argparse
import json
import re
import sys
import uuid
from pathlib import Path

# ------------------------------------------------------------------ settings

ARGS = None  # set in main()


def url_parts(path: str):
    # path is relative to the API root: "compendium/pois/{{poi_id}}". "../health" is outside the API root.
    if path.startswith("../"):
        segs = [s for s in path[3:].split("/") if s != ""]
    else:
        segs = [ARGS.api_var_ref] + [s for s in path.split("/") if s != ""]
    if path.endswith("/"):
        segs.append("")          # keep the trailing slash (profile/users/)
    return segs


def make_url(path: str, query=None):
    segs = url_parts(path)
    raw = f"{ARGS.scheme}://{ARGS.host_ref}:{ARGS.port_ref}/" + "/".join(segs)
    url = {
        "raw": raw,
        "protocol": ARGS.scheme,
        "host": [ARGS.host_ref],
        "port": ARGS.port_ref,
        "path": segs,
    }
    if query:
        url["query"] = query
        enabled = "&".join(f"{q['key']}={q['value']}" for q in query if not q.get("disabled"))
        if enabled:
            url["raw"] = raw + "?" + enabled
    return url


def script(lines):
    return {"type": "text/javascript", "exec": lines}


def event(listen, lines):
    return {"listen": listen, "script": script(lines)}


# ------------------------------------------------------------------ query parameters from OpenAPI

QUERY_PARAMS: dict = {}  # normalised key -> list of (name, description)


def norm_path(path: str) -> str:
    path = re.sub(r"\{\{[^}]+\}\}", "{x}", path)
    path = re.sub(r"\{[^}]+\}", "{x}", path)
    return path.strip("/")


def key_of(method: str, path: str) -> str:
    return f"{method.upper()} {norm_path(path)}"


def query_for(method: str, path: str, enabled=(), values=None):
    # enabled: {name: value} of the parameters that are switched on; values: {name: example} for the switched-off ones,
    # so a parameter only has to be ticked in Postman (no typing, no guessing of the format)
    out = []
    for name, schema in QUERY_PARAMS.get(key_of(method, path), []):
        q = {"key": name, "value": "", "description": schema}
        if name in enabled:
            q["value"] = enabled[name]
        else:
            q["disabled"] = True
            q["value"] = (values or {}).get(name, "")
        out.append(q)
    return out


# ------------------------------------------------------------------ request builder

REQUESTS: list = []  # (method, path) of every request built, for the coverage check
BODIES: dict = {}    # key_of(method, path) -> list of the raw JSON bodies built for it, for the asset-link check

# Body fields that point at an asset, and the variable the collection fills them from. A request body that carries one
# of these fields uses the variable; Upload photo (or the first photo of the list) fills it. Add a line here when the
# API gets a new asset field (for example avatar_photo_id on the profile).
ASSET_LINKS = {
    "main_photo_id": "photo_id",
    "avatar_photo_id": "photo_id",
    "icon_id": "icon_id",
}


def pretty(obj):
    # Raw JSON bodies are always written the same way: 4 spaces, one member per line (Postman shows them readable and the
    # Beautify button changes nothing).
    return json.dumps(obj, indent=4, ensure_ascii=False)


def tests_status(codes):
    if isinstance(codes, int):
        return [f'pm.test("Status code is {codes}", function () {{ pm.response.to.have.status({codes}); }});']
    lst = ", ".join(str(c) for c in codes)
    return [f'pm.test("Status code is one of {lst}", function () {{ pm.expect(pm.response.code).to.be.oneOf([{lst}]); }});']


def set_from_response(var, expr="jsonData.response_data.id"):
    return [
        "var jsonData = pm.response.json();",
        f'pm.environment.set("{var}", {expr});',
    ]


def request(name, method, path, *, body=None, form=None, test=None, status=200, desc="", pre=None,
            auth=True, enabled_query=(), query_values=None, headers=None):
    REQUESTS.append((method, path))
    item = {"name": name}
    events = []
    if pre:
        events.append(event("prerequest", pre))
    t = tests_status(status) + (test or [])
    events.append(event("test", t))
    item["event"] = events
    req = {"method": method, "header": list(headers or []), "url": make_url(path, query_for(method, path, enabled_query, query_values))}
    if body is not None:
        raw = body if isinstance(body, str) else pretty(body)
        BODIES.setdefault(key_of(method, path), []).append(raw)
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = {"mode": "raw", "raw": raw, "options": {"raw": {"language": "json"}}}
    if form is not None:
        req["body"] = {"mode": "formdata", "formdata": form}
    if not auth:
        req["auth"] = {"type": "noauth"}
    if desc:
        req["description"] = desc
    item["request"] = req
    return item


def folder(name, items, desc=""):
    f = {"name": name, "item": items}
    if desc:
        f["description"] = desc
    return f


# ------------------------------------------------------------------ reusable pieces

POINT = {"type": "Point", "coordinates": [13.3333, 47.3333]}
SAMPLE_PHOTO = "sample_photo.jpg"    # next to the collection; has a GPS position, altitude and capture time in its EXIF data
SAMPLE_GPX = "sample_track.gpx"      # next to the collection; made with scripts/make_sample_gpx.py --variant full
SAMPLE_ICON = "sample_icon.svg"      # next to the collection; a small clean outline icon (a mountain)
SAMPLE_ICONS_CSV = "icons_import.csv"   # next to the collection; the graphics of all 438 icons (scripts/make_icon_set.py)
CSV_NOTE = "Pick a CSV file in the body (key `file`). The header row must use the column names of the model; the Swagger page `/docs` lists them for this endpoint."


def csv_request(slug_path, label, status=(200, 201)):
    return request(
        f"Upload CSV ({label})", "POST", f"{slug_path}/upload-csv",
        form=[{"key": "file", "type": "file", "src": []}],
        status=list(status), desc=CSV_NOTE,
    )


FIRST_ID_LISTS: list = []   # (list path, variable) of every model; used by "Collect first IDs" and by the fallbacks below


def api_url(path):
    return f"{ARGS.scheme}://{ARGS.host_ref}:{ARGS.port_ref}/{ARGS.api_var_ref}/{path}"


def first_id_pre(list_path, var, *, second=None, extra=None):
    """Pre-request lines: when the variable is empty, fill it from the first row of the list (so the request can run alone,
    without Create or List before it). second is a second variable that gets the second row (event log compare);
    extra is a list of (variable, field) that are copied from the first row too (setting_value)."""
    lines = [
        f"// Run alone? When {{{{{var}}}}} is empty, take the id of the first row of {list_path}.",
        f'if (!pm.environment.get("{var}")) {{',
        "    pm.sendRequest({",
        f'        url: pm.variables.replaceIn("{api_url(list_path)}?limit={2 if second else 1}"),',
        '        method: "GET",',
        f'        header: {{ Authorization: "Bearer " + pm.environment.get("{ARGS.token_var}") }}',
        "    }, function (err, res) {",
        f'        if (err || res.code !== 200) {{ console.log("first id of {list_path}: the list answered " + (err || res.code)); return; }}',
        "        var rows = res.json().response_data;",
        "        if (rows && rows.length) {",
        f'            pm.environment.set("{var}", rows[0].{"key" if var == "setting_key" else "id"});',
    ]
    if second:
        lines.append(f'            if (rows.length > 1) {{ pm.environment.set("{second}", rows[1].id); }}')
    for v, field in (extra or []):
        lines.append(f'            pm.environment.set("{v}", JSON.stringify(rows[0].{field}));')
    lines += [
        f'            console.log("{var} was empty, using the first row of {list_path}: " + rows[0].{"key" if var == "setting_key" else "id"});',
        f'        }} else {{ console.log("first id of {list_path}: the list is empty"); }}',
        "    });",
        "}",
    ]
    return lines


def photo_link_pre(field="main_photo_id"):
    """Pre-request lines for a request whose body has the photo field `field` set to {{photo_id}}: when photo_id is empty the
    first photo of assets / photos is taken; when there is no photo at all the field is cut out of the body, so the request still
    works (without a photo). The body is written with the field first, so cutting it never leaves a stray comma."""
    return [
        "// Photo link: this body uses {{photo_id}}, the photo made by assets / photos / Upload photo.",
        '// Empty? The first photo you may read is taken. No photo at all? The field is left out of the body.',
        "function dropPhotoField() {",
        '    var raw = pm.request.body.raw || "";',
        f'    var cut = raw.replace(/"{field}"\\s*:\\s*"\\{{\\{{photo_id\\}}\\}}"\\s*,?\\s*/, "");',
        '    pm.request.body.update({ mode: "raw", raw: cut, options: { raw: { language: "json" } } });',
        "}",
        'if (!pm.environment.get("photo_id")) {',
        "    pm.sendRequest({",
        f'        url: pm.variables.replaceIn("{api_url("assets/photos")}?limit=1"),',
        '        method: "GET",',
        f'        header: {{ Authorization: "Bearer " + pm.environment.get("{ARGS.token_var}") }}',
        "    }, function (err, res) {",
        "        var rows = (!err && res.code === 200) ? res.json().response_data : [];",
        "        if (rows && rows.length) {",
        '            pm.environment.set("photo_id", rows[0].id);',
        '            console.log("photo_id was empty, using the first photo of assets/photos: " + rows[0].id);',
        "        } else {",
        '            console.log("photo_id is empty and no photo exists: " + "' + field + '" + " is left out. Run assets / photos / Upload photo first.");',
        "            dropPhotoField();",
        "        }",
        "    });",
        "}",
    ]


def uses_photo_test(field="main_photo_id"):
    return [
        'var wantedPhoto = pm.environment.get("photo_id");',
        f'if (wantedPhoto && pm.response.code < 300) {{ pm.test("{field} is the photo of assets / photos", function () {{ pm.expect(pm.response.json().response_data.{field}).to.eql(wantedPhoto); }}); }}',
    ]


def icon_link_pre(field="icon_id"):
    """Pre-request lines for a request whose body has `"icon_id": "{{icon_id}}"` as its FIRST member: when icon_id is empty the
    first icon of assets / icons is taken (the flags, when they are loaded); when there is no icon at all the field is cut out of
    the body (fine for countries and regions; reference values and resource types then answer 422, their icon is required).
    Same idea as photo_link_pre."""
    return [
        "// Icon link: this body uses {{icon_id}}, the icon made by assets / icons / Upload icon.",
        '// Empty? The first icon of assets / icons is taken. No icon at all? The field is left out of the body.',
        "function dropIconField() {",
        '    var raw = pm.request.body.raw || "";',
        f'    var cut = raw.replace(/"{field}"\\s*:\\s*"\\{{\\{{icon_id\\}}\\}}"\\s*,?\\s*/, "");',
        '    pm.request.body.update({ mode: "raw", raw: cut, options: { raw: { language: "json" } } });',
        "}",
        'if (!pm.environment.get("icon_id")) {',
        "    pm.sendRequest({",
        f'        url: pm.variables.replaceIn("{api_url("assets/icons")}?limit=1"),',
        '        method: "GET",',
        f'        header: {{ Authorization: "Bearer " + pm.environment.get("{ARGS.token_var}") }}',
        "    }, function (err, res) {",
        "        var rows = (!err && res.code === 200) ? res.json().response_data : [];",
        "        if (rows && rows.length) {",
        '            pm.environment.set("icon_id", rows[0].id);',
        '            console.log("icon_id was empty, using the first icon of assets/icons: " + rows[0].id);',
        "        } else {",
        '            console.log("icon_id is empty and no icon exists: " + "' + field + '" + " is left out. Run assets / icons / Upload icon first.");',
        "            dropIconField();",
        "        }",
        "    });",
        "}",
    ]


def uses_icon_test(field="icon_id"):
    return [
        'var wantedIcon = pm.environment.get("icon_id");',
        f'if (wantedIcon && pm.response.code < 300) {{ pm.test("{field} is the icon of assets / icons", function () {{ pm.expect(pm.response.json().response_data.{field}).to.eql(wantedIcon); }}); }}',
    ]


def icon_link():
    # the keyword arguments of crud_folder for a model that has icon_id (called when the folders are built, ARGS is set then)
    return dict(create_pre=icon_link_pre(), update_pre=icon_link_pre(), create_test=uses_icon_test(), update_test=uses_icon_test(),
                update_desc=("Only the fields in the body change. `icon_id` is `{{icon_id}}`, the icon made by assets / icons / Upload icon "
                             "(the first icon of the list when it is empty; the field is left out when there is no icon at all). "
                             "An unknown icon answers 422 (`icon_not_found`). On reference values and resource types the icon is required "
                             "(`null` answers 422); on countries and regions `null` removes the link."))


def crud_folder(app, slug, label, var, create_body, update_body, *, needs="", extras=None, csv=True,
                list_extra_test=None, create_pre=None, create_desc="", update_pre=None, create_test=None,
                update_test=None, update_desc=""):
    base = f"{app}/{slug}"
    FIRST_ID_LISTS.append((base, var))
    first = first_id_pre(base, var)
    needs_txt = f" Needs these variables first (run their Create): {needs}." if needs else ""
    items = [
        request(f"List {label}", "GET", base, enabled_query={},
                test=[
                    "var jsonData = pm.response.json();",
                    "pm.test(\"Response has a list in response_data\", function () { pm.expect(jsonData.response_data).to.be.an('array'); });",
                    f'if (!pm.environment.get("{var}") && jsonData.response_data.length) {{ pm.environment.set("{var}", jsonData.response_data[0].id); }}',
                ] + (list_extra_test or []),
                desc=f"All {label} you may read. Query parameters (limit, offset, ...) are listed but switched off."),
        request(f"Create {label}", "POST", base, body=create_body, status=201, pre=create_pre,
                test=set_from_response(var) + (create_test or []),
                desc=create_desc or f"Creates one record and saves its id in `{{{{{var}}}}}`.{needs_txt}"),
        request(f"Get one {label}", "GET", f"{base}/{{{{{var}}}}}", pre=first,
                desc=f"Uses `{{{{{var}}}}}` (set by Create, List or Collect first IDs; when empty the first row of the list is used)."),
        request(f"Update {label}", "PATCH", f"{base}/{{{{{var}}}}}", body=update_body, pre=first + (update_pre or []),
                test=update_test,
                desc=update_desc or ("Only the fields in the body change. When `{{" + var + "}}` is empty the first row of the list is changed.")),
    ]
    items += (extras or [])
    if csv:
        items.append(csv_request(base, label))
    items.append(request(f"Delete {label}", "DELETE", f"{base}/{{{{{var}}}}}", pre=SKIP_DELETES + first,
                         test=[f'pm.environment.unset("{var}");'],
                         desc=f"Deletes `{{{{{var}}}}}` and clears the variable. **When the variable is empty (no Create, List or Collect first IDs before) it deletes the FIRST row of the list.** Records that other records point at cannot be deleted until those are deleted."))
    return folder(slug, items)


SKIP_DELETES = [
    "// Collection Runner: set the variable skip_deletes to true to keep all records until the folder Cleanup (optional) runs.",
    'if (pm.environment.get("skip_deletes") === "true") { pm.execution.skipRequest(); }',
]


RANKED_TABLES = {"difficulty-levels", "difficulty-sports", "rarities", "visibilities"}   # the tables with a scale: rank is required


def ref_folder(slug, label, var, *, factor=True, extra_fields=None, name_required=False):
    body = {"icon_id": "{{icon_id}}", "name": "{{random_name}}", "name_de": "{{random_name}}", "color": "#2196F3"}
    if factor:
        body["point_factor"] = 1.0
    if slug in RANKED_TABLES:
        body["rank"] = 3
    body.update(extra_fields or {})
    upd = {"icon_id": "{{icon_id}}", "color": "#FF9800"}
    if factor:
        upd["point_factor"] = 2.0
    if slug in RANKED_TABLES:
        upd["rank"] = 4
    return crud_folder("core", slug, label, var, body, upd, **icon_link())


# ------------------------------------------------------------------ the folders

def core_folder():
    refs = [
        ("companies", "company", "company_id", False, None),
        ("gear-types", "gear type", "gear_type_id", False, None),
        ("achievement-categories", "achievement category", "achievement_category_id", True, None),
        ("achievement-scopes", "achievement scope", "achievement_scope_id", True, None),
        ("achievement-types", "achievement type", "achievement_type_id", True, None),
        ("compendium-types", "compendium type", "compendium_type_id", True, {"is_collectable": True}),
        ("difficulty-levels", "difficulty level", "difficulty_level_id", True, None),
        ("difficulty-sports", "difficulty sport", "difficulty_sport_id", True, None),
        ("point-reasons", "point reason", "point_reason_id", True, None),
        ("post-types", "post type", "post_type_id", True, None),
        ("rarities", "rarity", "rarity_id", True, None),
        ("region-types", "region type", "region_type_id", True, None),
        ("schedule-statuses", "schedule status", "schedule_status_id", True, None),
        ("snow-conditions", "snow condition", "snow_condition_id", True, None),
        ("sport-types", "sport type", "sport_type_id", True, None),
        ("trail-conditions", "trail condition", "trail_condition_id", True, None),
        ("visibilities", "visibility", "visibility_id", True, None),
        ("waypoint-types", "waypoint type", "waypoint_type_id", True, None),
        ("weather-conditions", "weather condition", "weather_condition_id", True, None),
    ]
    items = [ref_folder(slug, label, var, factor=f, extra_fields=extra) for slug, label, var, f, extra in refs]
    items.append(crud_folder(
        "core", "resource-types", "resource type", "resource_type_id",
        {"icon_id": "{{icon_id}}", "key": "{{random_key}}", "name": "{{random_name}}", "color": "#9C27B0"},
        {"icon_id": "{{icon_id}}", "name": "{{random_name}} renamed"},
        extras=None, **icon_link(),
    ))
    return folder("core", items, "Reference data (19 lookup tables) and resource types. Administrator for create, update, delete.")


def assets_folder():
    FIRST_ID_LISTS.append(("assets/photos", "photo_id"))
    FIRST_ID_LISTS.append(("assets/gpx", "gpx_id"))
    FIRST_ID_LISTS.append(("assets/icons", "icon_id"))
    icon_first = first_id_pre("assets/icons", "icon_id")
    # by-key requests: when icon_key is empty take the key of the first icon of the list
    icon_key_pre = [
        "// Run alone? When {{icon_key}} is empty, take the key of the first icon of assets/icons.",
        'if (!pm.environment.get("icon_key")) {',
        "    pm.sendRequest({",
        f'        url: pm.variables.replaceIn("{api_url("assets/icons")}?limit=1"),',
        '        method: "GET",',
        f'        header: {{ Authorization: "Bearer " + pm.environment.get("{ARGS.token_var}") }}',
        "    }, function (err, res) {",
        "        var rows = (!err && res.code === 200) ? res.json().response_data : [];",
        '        if (rows && rows.length) { pm.environment.set("icon_key", rows[0].key); console.log("icon_key was empty, using " + rows[0].key); }',
        '        else { console.log("icon_key is empty and no icon exists. Run assets / icons / Upload icon first."); }',
        "    });",
        "}",
    ]
    photo_first = first_id_pre("assets/photos", "photo_id")
    gpx_first = first_id_pre("assets/gpx", "gpx_id")

    def list_test(var):
        return ["var jsonData = pm.response.json();",
                'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                f'if (!pm.environment.get("{var}") && jsonData.response_data.length) {{ pm.environment.set("{var}", jsonData.response_data[0].id); }}']

    photos = folder("photos", [
        request("List photos", "GET", "assets/photos", test=list_test("photo_id"),
                desc="The photos you may read: your own and the public ones (an administrator sees all). Filters (switched off): `q`, `created_by`, `is_public`, "
                     "`altitude_min` / `altitude_max`, `taken_from` / `taken_to`, `created_from` / `created_to`, `bbox`, `near` + `radius_m`, `sort`."),
        request("Upload photo", "POST", "assets/photos", status=201,
                form=[{"key": "file", "type": "file", "src": SAMPLE_PHOTO},
                      {"key": "name", "value": "Postman photo {{random_name}}", "type": "text"},
                      {"key": "summary", "value": "Uploaded from Postman", "type": "text"},
                      {"key": "is_public", "value": "true", "type": "text"},
                      {"key": "name_de", "value": "", "type": "text", "disabled": True},
                      {"key": "summary_de", "value": "", "type": "text", "disabled": True},
                      {"key": "lon", "value": "13.35", "type": "text", "disabled": True},
                      {"key": "lat", "value": "47.33", "type": "text", "disabled": True},
                      {"key": "altitude_m", "value": "1800", "type": "text", "disabled": True},
                      {"key": "taken_at", "value": "2026-07-14T09:30:00Z", "type": "text", "disabled": True}],
                test=set_from_response("photo_id") + remember("created_photo_ids", "jsonData.response_data.id") + [
                    'pm.test("the photo is stored (relative path) and is public", function () { var p = jsonData.response_data; pm.expect(p.path).to.match(/^\\d{4}\\/\\d{2}\\/.+\\.(jpg|png|webp)$/); pm.expect(p.is_public).to.eql(true); });',
                    'pm.test("the position comes from the EXIF data of the file when the form gives none", function () { var p = jsonData.response_data; pm.expect(p).to.have.property("location"); });'],
                desc=(f"Multipart form. The body points at `{SAMPLE_PHOTO}` (put it in the Postman working directory, or pick any JPEG, PNG or WebP file in the body, key `file`). "
                      "Saves the id in `{{photo_id}}`: **from now on every request that has a photo field (the Create and Update calls of cards, POIs and posts: `main_photo_id`) uses this photo.** "
                      "The image is checked, turned upright, shrunk to 2560 px at most and saved without its metadata; position, altitude and capture time are read from EXIF "
                      "unless the (switched-off) form fields `lon` + `lat`, `altitude_m`, `taken_at` give them. `is_public` is true here so that every login (editor, viewer, guest) can use or see the photo.")),
        request("Get one photo", "GET", "assets/photos/{{photo_id}}", pre=photo_first,
                desc="Uses `{{photo_id}}` (when empty the first photo of the list). Add `?expand=created_by` for the owner."),
        request("Photo file (the image)", "GET", "assets/photos/{{photo_id}}/file", pre=photo_first,
                test=['pm.test("the answer is an image", function () { pm.expect(pm.response.headers.get("Content-Type")).to.match(/^image\\/(jpeg|png|webp)$/); });'],
                desc="The image itself (inline). Postman shows it in the Preview of the answer."),
        request("Update photo", "PATCH", "assets/photos/{{photo_id}}", pre=photo_first,
                body={"name": "Renamed {{random_name}}", "summary": "Changed from Postman", "is_public": True},
                desc="Name, texts (`name_de`, `summary_pl`, ...), `location` (GeoJSON point or null), `altitude_m`, `taken_at`, `is_public`. The image itself cannot be replaced: upload a new photo."),
        request("Delete photo", "DELETE", "assets/photos/{{photo_id}}", pre=SKIP_DELETES + photo_first, status=[200, 409],
                test=['if (pm.response.code === 200) { pm.environment.unset("photo_id"); }',
                      'pm.test("409 names who still uses the photo", function () { if (pm.response.code === 409) { pm.expect(pm.response.json().response_details.error_message).to.include("main photo"); } });'],
                desc="Deletes the photo and its file and clears `photo_id`. **409** while a card, POI, post, gear, segment or track still has it as its main photo "
                     "(use \"Remove the main photo\" in those folders first). When `photo_id` is empty it deletes the FIRST photo of the list."),
    ], "Photo files (JPEG, PNG, WebP). Upload photo saves `photo_id`; the requests that can carry a photo use it.")

    gpx = folder("gpx", [
        request("List GPX files", "GET", "assets/gpx", test=list_test("gpx_id"),
                desc="The stored GPX files you may read (own, public; an administrator sees all). Filters (switched off): `q`, `created_by`, `is_public`, `sha256` (duplicates), "
                     "`created_from` / `created_to`, `sort`. A GPX file is made by `explorer / tracks / Upload track`, not here."),
        request("Get one GPX file", "GET", "assets/gpx/{{gpx_id}}", pre=gpx_first,
                desc="Uses `{{gpx_id}}` (set by Upload track, Get one track or List GPX files). Add `?expand=created_by` for the owner."),
        request("Download GPX file", "GET", "assets/gpx/{{gpx_id}}/file", pre=gpx_first,
                test=['pm.test("the answer is a GPX file", function () { pm.expect(pm.response.headers.get("Content-Type")).to.include("gpx"); pm.expect(pm.response.text()).to.include("<gpx"); });'],
                desc="The original file as it was uploaded."),
        request("Update GPX file", "PATCH", "assets/gpx/{{gpx_id}}", pre=gpx_first,
                body={"name": "Renamed {{random_name}}", "summary": "Changed from Postman"},
                desc="Name, texts and `is_public`. The file itself cannot be replaced."),
        request("Delete GPX file", "DELETE", "assets/gpx/{{gpx_id}}", pre=SKIP_DELETES + gpx_first, status=[200, 409],
                test=['if (pm.response.code === 200) { pm.environment.unset("gpx_id"); }'],
                desc="Deletes a GPX file that no track uses any more. **409** while a track (or its geometry) uses it: delete or archive-and-remove the track first. "
                     "When `gpx_id` is empty it tries the FIRST file of the list."),
    ], "The original GPX files of the tracks. They are created by Upload track.")
    icons = folder("icons", [
        request("List icons", "GET", "assets/icons", test=list_test("icon_id"),
                desc="The icons (SVG pictures: flags and symbols) without their SVG text. Everybody who is logged in may read them. Filters (switched off): `q`, `key`, "
                     "`key_prefix` (for example `flag_` or `sport_`), `created_by`, `created_from` / `created_to`, `sort` (`key`, `name`, `created_at`, `updated_at`)."),
        request("Upload icon", "POST", "assets/icons", status=201,
                form=[{"key": "file", "type": "file", "src": SAMPLE_ICON},
                      {"key": "key", "value": "{{random_key}}", "type": "text"},
                      {"key": "name", "value": "Postman icon {{random_name}}", "type": "text"},
                      {"key": "summary", "value": "Uploaded from Postman", "type": "text"},
                      {"key": "name_de", "value": "", "type": "text", "disabled": True},
                      {"key": "summary_de", "value": "", "type": "text", "disabled": True}],
                test=set_from_response("icon_id") + ['pm.environment.set("icon_key", jsonData.response_data.key);'] + remember("created_icon_ids", "jsonData.response_data.id") + [
                    'pm.test("the icon has a key in lower case and a SHA-256", function () { var i = jsonData.response_data; pm.expect(i.key).to.match(/^[a-z0-9_.-]+$/); pm.expect(i.sha256).to.have.lengthOf(64); });',
                    'pm.test("the answer lists what the cleaning removed (nothing for the sample file)", function () { pm.expect(jsonData.response_details.removed).to.be.an("array").that.is.empty; });'],
                desc=(f"Multipart form (admin only). The body points at `{SAMPLE_ICON}` (put it in the Postman working directory, or pick any SVG file, key `file`). "
                      "Saves the id in `{{icon_id}}` and the key in `{{icon_key}}`: **from now on every request that has `icon_id` (the Create and Update calls of the reference tables, "
                      "resource types, countries and regions) uses this icon.** The SVG is cleaned before it is stored: script, `<style>`, `<foreignObject>`, animation, event handlers, "
                      "links to other files and foreign namespaces are removed and listed in `response_details.removed`. `key` is the name icons are found by (lower-case letters, "
                      "digits and `_ . -`; default: the file name); the same key twice answers 409. The limit is 300 KB (`ICON_MAX_UPLOAD_KB`).")),
        request("Upload icons CSV (dry run)", "POST", "assets/icons/upload-csv", status=[200, 201],
                form=[{"key": "file", "type": "file", "src": SAMPLE_ICONS_CSV}],
                enabled_query={"dry_run": "true"}, query_values={"update": "true", "link": "false"},
                test=['var jsonData = pm.response.json();',
                      'pm.test("dry run: every row is usable, nothing is saved", function () { var r = jsonData.response_data; pm.expect(r.dry_run).to.eql(true); pm.expect(r.rejected).to.eql(0); pm.expect(r.errors).to.be.empty; });',
                      'pm.test("the counts add up to the rows of the file", function () { var r = jsonData.response_data; pm.expect(r.inserted + r.updated + r.unchanged).to.be.above(0); });'],
                desc=(f"Admin only. Multipart form: the CSV `{SAMPLE_ICONS_CSV}` (next to the collection; the graphics of all icons, made by `scripts/make_icon_set.py`; put it in the Postman working directory "
                      "or pick your own file, key `file`). **`dry_run=true` checks and counts everything and saves nothing**: run this first. The answer: `inserted` (new keys), `updated`, `unchanged`, "
                      "`rejected` with `errors` (one text per wrong row, by row number), `notes` (what the cleaner took out of an SVG), and with `link=true` (the default) `linked` and `still_without_icon` per table. "
                      "Switched-off parameters: `update` (replace icons whose key exists), `link` (default on).")),
        request("Upload icons CSV (import all)", "POST", "assets/icons/upload-csv", status=[200, 201],
                form=[{"key": "file", "type": "file", "src": SAMPLE_ICONS_CSV}],
                query_values={"update": "true", "dry_run": "true", "link": "false"},
                test=['var jsonData = pm.response.json();',
                      'pm.test("import: no row was rejected", function () { var r = jsonData.response_data; pm.expect(r.dry_run).to.eql(false); pm.expect(r.rejected).to.eql(0); pm.expect(r.errors).to.be.empty; });',
                      'pm.test("a second run creates nothing new (the keys exist)", function () { var r = jsonData.response_data; pm.expect(r.inserted + r.updated + r.unchanged).to.be.above(0); });'],
                desc=(f"**Creates every icon of the CSV `{SAMPLE_ICONS_CSV}` in one call** (admin only): the 438 icons of the reference tables and resource types, each cleaned like an upload and with its names in English, German and Polish. "
                      "An icon whose key exists is left alone (`unchanged`), so the call can be run again. With `link=true` (the default) every country (`flag_at`) and region without a flag whose ISO code matches "
                      "the key of an icon then gets its `icon_id` (the answer lists how many per table). Switched-off parameters to try: `update=true` replaces icons that exist (SVG and names) when they differ; "
                      "`dry_run=true` only counts; `link=false` skips the linking. Run `Upload icons CSV (dry run)` before the first real import.")),
        request("Link rows to icons by key", "POST", "assets/icons/link", status=200,
                query_values={"dry_run": "true"},
                test=['var jsonData = pm.response.json();',
                      'pm.test("the answer lists what was linked and what still has no icon", function () { var r = jsonData.response_data; pm.expect(r.linked).to.be.an("object"); pm.expect(r.still_without_icon).to.be.an("object"); });'],
                desc="Admin only. Sets `icon_id` on every country and region that has none and whose ISO code (countries: `flag_<iso code>`) or "
                     "ISO 3166-2 code (regions: `flag_ch_zh`) matches the **key** of an icon: the API version of `scripts/sql/icons_link.sql`. A link that is set is never changed, so it can be run again after every import. "
                     "`dry_run=true` (switched off here) counts without saving. `still_without_icon` shows how many countries and regions have no flag yet."),
        request("Get one icon", "GET", "assets/icons/{{icon_id}}", pre=icon_first,
                desc="Uses `{{icon_id}}` (when empty the first icon of the list). The JSON has no SVG text: see \"Icon file\". Add `?expand=created_by` for the owner."),
        request("Icon file (the SVG)", "GET", "assets/icons/{{icon_id}}/file", pre=icon_first,
                test=['pm.test("the answer is an SVG with a version tag and safe headers", function () {',
                      '    pm.expect(pm.response.headers.get("Content-Type")).to.include("image/svg+xml");',
                      '    pm.expect(pm.response.headers.get("ETag")).to.match(/^"[0-9a-f]{64}"$/);',
                      '    pm.expect(pm.response.headers.get("X-Content-Type-Options")).to.eql("nosniff");',
                      '    pm.expect(pm.response.headers.get("Content-Security-Policy")).to.include("sandbox");',
                      '    pm.expect(pm.response.text()).to.include("<svg");',
                      "});"],
                desc="The picture as stored (inline). Postman shows it in the Preview of the answer. The `ETag` is the SHA-256 of the text: send it back in the header `If-None-Match` to get 304."),
        request("Icon file as PNG", "GET", "assets/icons/{{icon_id}}/file", pre=icon_first,
                enabled_query={"format": "png", "size": "64"},
                test=['pm.test("the answer is a PNG", function () { pm.expect(pm.response.headers.get("Content-Type")).to.eql("image/png"); });'],
                desc="The same icon drawn as a PNG: `format=png`, `size` = width in pixels (16 to 1024, default 64; the height follows the shape)."),
        request("Icon file by key", "GET", "assets/icons/by-key/{{icon_key}}/file", pre=icon_key_pre,
                test=['pm.test("the answer is an SVG", function () { pm.expect(pm.response.headers.get("Content-Type")).to.include("image/svg+xml"); });'],
                desc="The icon found by its key instead of its id, for example `flag_at` or `sport_hiking` (the text still in the `icon` column of the reference tables). "
                     "Uses `{{icon_key}}` (set by Upload icon; when empty the first icon of the list). Upper case is read as lower case. `format` and `size` work here too."),
        request("Replace the SVG of an icon", "PUT", "assets/icons/{{icon_id}}/file", pre=icon_first,
                form=[{"key": "file", "type": "file", "src": SAMPLE_ICON}],
                test=['var jsonData = pm.response.json();',
                      'pm.test("the icon keeps its id and key and has a SHA-256", function () { pm.expect(jsonData.response_data.id).to.eql(pm.environment.get("icon_id")); pm.expect(jsonData.response_data.sha256).to.have.lengthOf(64); });'],
                desc="Admin only. Replaces the picture of `{{icon_id}}`; the id, the key and every link stay, so every country, region and reference value that uses the icon shows the new picture. Cleaned like an upload."),
        request("Update icon", "PATCH", "assets/icons/{{icon_id}}", pre=icon_first,
                body={"name": "Renamed {{random_name}}", "summary": "Changed from Postman"},
                desc="Names, summaries and `key` (lower case; 409 when the key exists; links are by id, so a new key breaks nothing). The SVG is replaced with \"Replace the SVG of an icon\"."),
        request("Delete icon", "DELETE", "assets/icons/{{icon_id}}", pre=SKIP_DELETES + icon_first, status=[200, 409],
                test=['if (pm.response.code === 200) { pm.environment.unset("icon_id"); pm.environment.unset("icon_key"); }',
                      'pm.test("409 names who still uses the icon", function () { if (pm.response.code === 409) { pm.expect(pm.response.json().response_details.error_message).to.include("is used by"); } });'],
                desc="Deletes the icon and clears `icon_id` and `icon_key`. **409** while a country, region or reference value still uses it (the answer says how many of which). "
                     "When `icon_id` is empty it deletes the FIRST icon of the list."),
    ], "SVG icons and flags. Upload icon saves `icon_id` and `icon_key`; the Create and Update calls of the reference tables, resource types, countries and regions use `icon_id`.")
    return folder("assets", [photos, gpx, icons],
                  "Files that other records point at: photos, GPX files and icons. Upload photo saves `photo_id`, Upload track saves `gpx_id`, Upload icon saves `icon_id`.")


PHOTO_UPDATE_DESC = ("Only the fields in the body change. `main_photo_id` is `{{photo_id}}`, the photo made by assets / photos / Upload photo "
                     "(the first photo of the list when it is empty; the field is left out when there is no photo at all). "
                     "A photo you may not read, or an unknown one, answers 422.")


def remove_photo(label, base, var):
    # PATCH main_photo_id = null: a photo can only be deleted (assets / photos / Delete photo) when nothing uses it as its main photo
    return request(f"Remove the main photo of the {label}", "PATCH", f"{base}/{{{{{var}}}}}", body={"main_photo_id": None},
                   pre=first_id_pre(base, var),
                   test=['pm.test("main_photo_id is empty now", function () { pm.expect(pm.response.json().response_data.main_photo_id).to.eql(null); });'],
                   desc=f"Clears the main photo of the {label}. A photo can only be deleted while no card, POI, post, gear, segment or track uses it as its main photo.")


def compendium_folder():
    country = crud_folder(
        "compendium", "countries", "country", "country_id",
        {"icon_id": "{{icon_id}}", "name": "{{random_name}}", "iso_code": "{{random_iso_code}}", "location": POINT, "capital": "Test City"},
        {"icon_id": "{{icon_id}}", "capital": "Updated City"}, **icon_link())
    region = crud_folder(
        "compendium", "regions", "region", "region_id",
        {"icon_id": "{{icon_id}}", "name": "{{random_name}}", "location": POINT, "country_id": "{{country_id}}", "region_type_id": "{{region_type_id}}"},
        {"icon_id": "{{icon_id}}", "summary": "Updated summary"}, needs="`country_id` (compendium/countries), `region_type_id` (core/region-types)", **icon_link())
    poi_rescan = request("Rescan POI", "POST", "compendium/pois/{{poi_id}}/rescan", status=202, pre=first_id_pre("compendium/pois", "poi_id"),
                         test=[
                             "var jsonData = pm.response.json();",
                             'pm.environment.set("job_id", jsonData.response_data.job_id);',
                             'pm.test("Location header points to the job", function () { pm.expect(pm.response.headers.get("Location")).to.include("/management/my-jobs/"); });',
                         ],
                         desc="Starts a background job that matches existing visits against this POI. Saves `job_id`; follow it with management/my-jobs.")
    poi = crud_folder(
        "compendium", "pois", "POI", "poi_id",
        {"main_photo_id": "{{photo_id}}", "name": "{{random_name}}", "location": POINT, "compendium_type_id": "{{compendium_type_id}}",
         "main_region_id": "{{region_id}}", "altitude_m": 2000},
        {"main_photo_id": "{{photo_id}}", "altitude_m": 2100},
        needs="`compendium_type_id` (core/compendium-types), `region_id` (compendium/regions); the photo comes from `photo_id` (assets / photos / Upload photo)",
        extras=[poi_rescan, remove_photo("POI", "compendium/pois", "poi_id")],
        create_pre=photo_link_pre(), update_pre=photo_link_pre(), create_test=uses_photo_test(), update_test=uses_photo_test(),
        update_desc=PHOTO_UPDATE_DESC)
    card_rescan = request("Rescan card", "POST", "compendium/cards/{{card_id}}/rescan", status=202, pre=first_id_pre("compendium/cards", "card_id"),
                          test=[
                              "var jsonData = pm.response.json();",
                              'pm.environment.set("job_id", jsonData.response_data.job_id);',
                          ],
                          desc="Starts a background job for this card. Saves `job_id`.")
    card_render = request("Card graphic (render)", "GET", "compendium/cards/{{card_id}}/render", pre=first_id_pre("compendium/cards", "card_id"),
                          enabled_query={"format": "svg", "lang": "en"},
                          # example values of the switched-off parameters: tick one in Postman and it works
                          query_values={"ratio": "63:88", "style": "3d", "dpi": "300", "download": "true"},
                          test=['pm.test("an image or the card as JSON", function () { var t = pm.response.headers.get("Content-Type") || ""; pm.expect(t).to.match(/svg|png|jpeg|pdf|json/); });'],
                          desc="The card as printed. The picture is the main photo of the card; a card without its own photo uses the main photo of its POI.\n\n"
                               "Query parameters (the two switched on are the defaults; tick the others to try them, each has an example value):\n"
                               "- `format`: json (every value on the card, translated), svg, png, jpg or pdf (print, 3 mm bleed). Default svg.\n"
                               "- `lang`: en, de or pl, the language of every text on the card. A text empty in that language comes from the next one (en, de, pl).\n"
                               "- `ratio`: shape as width:height, whole numbers 1 to 100, between 2:5 and 5:2. Default 63:88 (trading card); also 1:1, 4:5, 9:16, 3:2, 16:9. "
                               "The shorter side is always 63 mm. From 13:10 on the photo moves to the left of the texts.\n"
                               "- `style`: look of the card, `standard` (default) or `3d` (raised frame, glass panels, holographic sheen). Another name answers 422.\n"
                               "- `dpi`: sharpness of a png or jpg, 72 to 2000, default 300 (815 x 1110 px on 63:88; 600 gives twice the width and height). "
                               "The jpg records it. Wide or tall shapes have more pixels, so very high values answer 422 with the highest dpi that fits "
                               "(63:88 up to 2000, 16:9 up to 1990, 5:2 up to 1690). Ignored for svg, pdf and json.\n"
                               "- `download`: true saves the file instead of showing it.\n\n"
                               "Only 63:88, standard style, 300 dpi is stored by the render job and served from disk when up to date; everything else is drawn on request "
                               "(a 2000 dpi picture takes several seconds). The file name says what was asked: `card-00013-en.svg`, `card-00013-de-2x3-3d.jpg`, "
                               "`card-00013-en-600dpi.png`. Any other query parameter answers 422.")
    card_render_job = request("Render the card files again (job)", "POST", "compendium/cards/{{card_id}}/render", status=[202, 409],
                              pre=first_id_pre("compendium/cards", "card_id"),
                              test=["var jsonData = pm.response.json();",
                                    'if (pm.response.code === 202) { pm.environment.set("job_id", jsonData.response_data.job_id); }'],
                              desc="Starts a job that writes SVG, PNG, JPG and PDF in English, German and Polish (63:88, standard style, 300 dpi). Saves `job_id`. 409 when a render is already queued or running "
                                   "(a card made or changed a moment ago already has one).")
    card = crud_folder(
        "compendium", "cards", "card", "card_id",
        {"main_photo_id": "{{photo_id}}", "name": "{{random_name}}", "poi_id": "{{poi_id}}"},
        {"main_photo_id": "{{photo_id}}", "name": "{{random_name}} renamed"},
        needs="`poi_id` (compendium/pois); the photo comes from `photo_id` (assets / photos / Upload photo)",
        extras=[card_rescan, card_render, card_render_job, remove_photo("card", "compendium/cards", "card_id")],
        create_pre=photo_link_pre(), update_pre=photo_link_pre(), create_test=uses_photo_test(), update_test=uses_photo_test(),
        update_desc=PHOTO_UPDATE_DESC)
    post = crud_folder(
        "compendium", "posts", "post", "post_id",
        {"main_photo_id": "{{photo_id}}", "name": "{{random_name}}", "post_type_id": "{{post_type_id}}"},
        {"main_photo_id": "{{photo_id}}", "summary": "Updated summary"},
        needs="`post_type_id` (core/post-types); the photo comes from `photo_id` (assets / photos / Upload photo)",
        extras=[remove_photo("post", "compendium/posts", "post_id")],
        create_pre=photo_link_pre(), update_pre=photo_link_pre(), create_test=uses_photo_test(), update_test=uses_photo_test(),
        update_desc=PHOTO_UPDATE_DESC)
    poi_region = crud_folder(
        "compendium", "poi-regions", "POI-region link", "poi_region_id",
        {"poi_id": "{{poi_id}}", "region_id": "{{region_id}}", "slot_position": 2}, {"slot_position": 3},
        needs="`poi_id` (compendium/pois), `region_id` (compendium/regions)")
    return folder("compendium", [country, region, poi, card, post, poi_region],
                  "Geographic and editorial catalog. Order of Create calls: core region-types, compendium-types, post-types, then country, region, POI, card, post, POI-region link.")


def explorer_folder():
    gear = crud_folder(
        "explorer", "gear", "gear", "gear_id",
        {"name": "{{random_name}}", "company_id": "{{company_id}}", "gear_type_id": "{{gear_type_id}}",
         "model": "Test model", "weight_g": 500},
        {"weight_g": 450}, needs="`company_id` (core/companies), `gear_type_id` (core/gear-types)")
    FIRST_ID_LISTS.append(("explorer/tracks", "track_id"))
    track_first = first_id_pre("explorer/tracks", "track_id")
    gpx_note = (f"The body points at `{SAMPLE_GPX}` (put it in the Postman working directory, or pick any .gpx file in the body, key `gpx_file`). "
                "`python scripts/make_sample_gpx.py --variant full --out full.gpx` makes another one.")
    track_gpx_id = [
        "// The stored GPX file is an asset of its own (assets / gpx). Save its id in gpx_id.",
        "pm.sendRequest({",
        f'    url: pm.variables.replaceIn("{api_url("explorer/tracks")}/" + jsonData.response_data.id),',
        '    method: "GET",',
        f'    header: {{ Authorization: "Bearer " + pm.environment.get("{ARGS.token_var}") }}',
        "}, function (err, res) {",
        '    if (!err && res.code === 200 && res.json().response_data.gpx_id) { pm.environment.set("gpx_id", res.json().response_data.gpx_id); }',
        "});",
    ]
    tracks = folder("tracks", [
        request("List tracks", "GET", "explorer/tracks",
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                    'if (!pm.environment.get("track_id") && jsonData.response_data.length) { pm.environment.set("track_id", jsonData.response_data[0].id); }',
                ], desc="Your tracks. Switch on `archived` to see archived ones."),
        request("Upload track (GPX)", "POST", "explorer/tracks", status=202,
                form=[{"key": "name", "value": "Postman track {{random_name}}", "type": "text"},
                      {"key": "gpx_file", "type": "file", "src": SAMPLE_GPX},
                      {"key": "summary", "value": "Uploaded from Postman", "type": "text"},
                      {"key": "is_public", "value": "false", "type": "text"}],
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.environment.set("track_id", jsonData.response_data.id);',
                    'pm.environment.set("job_id", jsonData.response_data.job_id);',
                    'pm.test("Location header points to the job", function () { pm.expect(pm.response.headers.get("Location")).to.include("/management/my-jobs/"); });',
                ] + track_gpx_id,
                desc=f"Accepts the file and starts processing as a job (202). Saves `track_id`, `job_id` and `gpx_id` (the stored file, see assets / gpx). {gpx_note}"),
        request("Get one track", "GET", "explorer/tracks/{{track_id}}", pre=track_first,
                test=['var gpxOfTrack = pm.response.json().response_data.gpx_id;',
                      'if (gpxOfTrack) { pm.environment.set("gpx_id", gpxOfTrack); }'],
                desc="Also saves `gpx_id`, the stored GPX file of the track (assets / gpx)."),
        request("Track geometry", "GET", "explorer/tracks/{{track_id}}/geometry", status=[200, 404], pre=track_first,
                desc="404 until the processing job has finished."),
        request("Track performance", "GET", "explorer/tracks/{{track_id}}/performance", status=[200, 404], pre=track_first,
                desc="404 when the file has no timestamps or the job is not finished."),
        request("Update track", "PATCH", "explorer/tracks/{{track_id}}", body={"name": "Renamed {{random_name}}", "is_public": False}, pre=track_first),
        request("Reprocess track", "POST", "explorer/tracks/{{track_id}}/reprocess", status=[202, 409], pre=track_first,
                desc="Only tracks with processing_status `failed` can be reprocessed (409 otherwise).",
                test=["var jsonData = pm.response.json();",
                      'if (pm.response.code === 202) { pm.environment.set("job_id", jsonData.response_data.job_id); }']),
        request("Archive track (DELETE)", "DELETE", "explorer/tracks/{{track_id}}", pre=track_first,
                desc="Archives the track (it is not deleted). Restore brings it back."),
        request("Restore track", "POST", "explorer/tracks/{{track_id}}/restore", pre=track_first),
    ])
    segments = segments_folder()
    routes = routes_folder()
    return folder("explorer", [gear, tracks, segments, routes],
                  "User activity data (gear, tracks) and the planned hierarchy: segments are pieces of trail with their own geometry, routes are chains of segments.")


def remember(var, expr):
    # test lines: add an id to the list kept in the environment variable `var` (a JSON array), for the Cleanup folder
    return [f'var list_ = JSON.parse(pm.environment.get("{var}") || "[]"); list_.push({expr}); pm.environment.set("{var}", JSON.stringify(list_));']


def delete_all_pre(var, path):
    # pre-request lines of a Cleanup request: delete every record whose id is in the list `var`, one after the other
    return [
        f"// Deletes everything this collection made in {path} (the ids are kept in {var}); answers are not checked.",
        f'var ids = JSON.parse(pm.environment.get("{var}") || "[]");',
        f'var token = pm.environment.get("{ARGS.token_var}");',
        f'var base = pm.variables.replaceIn("{api_url(path)}/");',
        "function next() {",
        "    var id = ids.shift();",
        f'    if (!id) {{ pm.environment.set("{var}", "[]"); return; }}',
        '    pm.sendRequest({ url: base + id, method: "DELETE", header: { Authorization: "Bearer " + token } }, function () { next(); });',
        "}",
        "next();",
    ]


def drawn_trail(first, count):
    # points of a drawn trail, about 100 m apart and climbing 12 m each: [[lon, lat, ele], ...]; the trail of `first`+count points
    # continues the one that ends at point `first` (same coordinates), so segments built from consecutive parts are connected
    return [[round(11.87 + i * 0.0002, 5), round(47.05 + i * 0.0009, 5), 1800 + i * 12] for i in range(first, first + count)]


def segments_folder():
    FIRST_ID_LISTS.append(("explorer/segments", "segment_id"))
    first = first_id_pre("explorer/segments", "segment_id")
    gpx_note = (f"The body points at `{SAMPLE_GPX}` (put it in the Postman working directory, or pick any .gpx file in the body, key `gpx_file`). "
                "Times and heart rate in the file are dropped; the file itself is not kept.")
    sport = "`sport_type_id` (core/sport-types; Create sport type, or Collect first IDs)"
    return folder("segments", [
        request("List segments", "GET", "explorer/segments",
                test=["var jsonData = pm.response.json();",
                      'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                      'if (!pm.environment.get("segment_id") && jsonData.response_data.length) { pm.environment.set("segment_id", jsonData.response_data[0].id); }'],
                desc="The segments you may read: your own and the public ones. Filters (switched off): `near` + `radius_m` finds segments that start or end near a point, "
                     "`unused`, `created_by`, `sport_type_id`, `distance_min` / `distance_max`, `sort`."),
        request("Create segment from a GPX file", "POST", "explorer/segments", status=201,
                form=[{"key": "name", "value": "Postman segment {{random_name}}", "type": "text"},
                      {"key": "gpx_file", "type": "file", "src": SAMPLE_GPX},
                      {"key": "sport_type_id", "value": "{{sport_type_id}}", "type": "text"},
                      {"key": "is_public", "value": "false", "type": "text"}],
                test=set_from_response("segment_id") + remember("created_segment_ids", "jsonData.response_data.id") + [
                    'pm.test("the new segment has a distance and is private", function () { var s = jsonData.response_data; pm.expect(s.metrics.distance_m).to.be.above(0); pm.expect(s.is_public).to.eql(false); });'],
                desc=f"Makes a segment from your GPX file and saves its id in `{{{{segment_id}}}}`. {gpx_note} Needs {sport}."),
        request("Create segment from drawn points", "POST", "explorer/segments/from-coordinates", status=201,
                body={"name": "Postman drawn segment {{random_name}}", "sport_type_id": "{{sport_type_id}}", "is_public": False,
                      "coordinates": drawn_trail(0, 10)},
                test=set_from_response("segment_id") + remember("created_segment_ids", "jsonData.response_data.id") + [
                    'pm.test("about 900 m, with elevation", function () { var m = jsonData.response_data.metrics; pm.expect(m.distance_m).to.be.within(800, 1100); pm.expect(m.elevation_gain_m).to.be.above(50); });'],
                desc=f"Points are [lon, lat, ele]; 2 to 5000 points. Saves `{{{{segment_id}}}}`. Needs {sport}."),
        request("Create segment from a track", "POST", "explorer/segments/from-track", status=[201, 404, 409, 422],
                body={"name": "Postman clip {{random_name}}", "sport_type_id": "{{sport_type_id}}", "track_id": "{{track_id}}",
                      "start_distance_m": 0, "end_distance_m": 1000},
                test=["var jsonData = pm.response.json();",
                      'if (pm.response.code === 201) { pm.environment.set("segment_id", jsonData.response_data.id); }',
                      'if (pm.response.code === 201) { var list_ = JSON.parse(pm.environment.get("created_segment_ids") || "[]"); list_.push(jsonData.response_data.id); pm.environment.set("created_segment_ids", JSON.stringify(list_)); }'],
                desc="A part of one of YOUR OWN tracks, cut by distance from its start (here the first 1000 m). Needs `{{track_id}}` of a track with "
                     "processing_status ready (404 for somebody else's track, 409 while it is not processed, 422 behind the end of the track)."),
        request("Get one segment", "GET", "explorer/segments/{{segment_id}}", pre=first,
                desc="Add `?expand=sport_type,difficulty_level,difficulty_sport,start_poi,end_poi,created_by` for the linked objects."),
        request("Segment geometry", "GET", "explorer/segments/{{segment_id}}/geometry", pre=first,
                desc="The GeoJSON line, the elevation profile and the start and end point."),
        request("Update segment", "PATCH", "explorer/segments/{{segment_id}}", pre=first,
                body={"summary": "Changed from Postman"},
                desc="Metadata only; the geometry of a segment never changes. `is_public: false` is refused (409) while another user's route or a public route uses it."),
        request("Delete segment", "DELETE", "explorer/segments/{{segment_id}}", pre=SKIP_DELETES + first, status=[200, 409],
                test=['if (pm.response.code === 200) { pm.environment.unset("segment_id"); }'],
                desc="409 when a route uses the segment (the answer says how many routes; it names only the ones you may see). Delete the route first."),
    ], "Pieces of trail with their own geometry. A segment is never changed once it exists (draw a new one instead).")


def routes_folder():
    FIRST_ID_LISTS.append(("explorer/routes", "route_id"))
    first = first_id_pre("explorer/routes", "route_id")
    walk = lambda **kw: {"slot_position": 0, "is_default": True, "is_reversed": False, **kw}
    return folder("routes", [
        request("List routes", "GET", "explorer/routes",
                test=["var jsonData = pm.response.json();",
                      'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                      'if (!pm.environment.get("route_id") && jsonData.response_data.length) { pm.environment.set("route_id", jsonData.response_data[0].id); }'],
                desc="The routes you may read: your own and the public ones. Filters (switched off): `sport_type_id`, `difficulty_level_id`, `distance_min` / `distance_max`, `q`, `sort`."),
        request("1. Create route (a draft without segments)", "POST", "explorer/routes", status=201,
                body={"name": "Postman route {{random_name}}", "summary": "Made from Postman"},
                test=set_from_response("route_id") + remember("created_route_ids", "jsonData.response_data.id") + [
                    'pm.test("a draft has no sport, no difficulty and no totals", function () { var r = jsonData.response_data; pm.expect(r.sport_type_id).to.eql(null); pm.expect(r.agg_distance_m).to.eql(null); pm.expect(r.segments).to.eql([]); });'],
                desc="Step 1 of the test with a GPX file: make the route. Saves `{{route_id}}`. Sport and difficulty stay empty until segments are added."),
        request("2. Put the segment into the route", "PUT", "explorer/routes/{{route_id}}/segments",
                body={"segments": [walk(segment_id="{{segment_id}}")], "validation": "strict"},
                test=["var jsonData = pm.response.json();",
                      'pm.test("totals and sport come from the segment", function () { var r = jsonData.response_data; pm.expect(r.segments.length).to.eql(1); pm.expect(r.agg_distance_m).to.be.above(0); pm.expect(r.sport_type_id).to.not.eql(null); });'],
                desc="Step 2 (after `Create segment from a GPX file`): `{{segment_id}}` becomes slot 0 of the route. The list you send REPLACES the saved one. "
                     "The server checks the slots and that neighbouring segments connect (within 50 m or at the same POI), recomputes distance and elevation, and fills sport and difficulty if they are empty."),
        request("2b. Draw two segments inside the save", "PUT", "explorer/routes/{{route_id}}/segments",
                body={"segments": [
                    walk(inline={"name": "Drawn A {{random_name}}", "sport_type_id": "{{sport_type_id}}", "coordinates": drawn_trail(0, 10)}),
                    walk(slot_position=1, inline={"name": "Drawn B {{random_name}}", "sport_type_id": "{{sport_type_id}}", "coordinates": drawn_trail(9, 10)}),
                ], "validation": "strict"},
                test=["var jsonData = pm.response.json();",
                      'jsonData.response_data.created_segments.forEach(function (c) { var list_ = JSON.parse(pm.environment.get("created_segment_ids") || "[]"); list_.push(c.segment_id); pm.environment.set("created_segment_ids", JSON.stringify(list_)); });',
                      'pm.test("two segments were created and the route has about 1800 m", function () { var r = jsonData.response_data; pm.expect(r.created_segments.length).to.eql(2); pm.expect(r.agg_distance_m).to.be.within(1600, 2100); });'],
                desc="Drawn trails can be saved together with the route in one call (`inline`); `created_segments` gives the ids of the new segments by position. "
                     "Instead of `coordinates` an inline item can name `track_id`, `start_distance_m`, `end_distance_m` (a part of your own track). "
                     "If anything is wrong nothing is saved, not even the new segments."),
        request("Validate segments (nothing is saved)", "POST", "explorer/routes/{{route_id}}/segments/validate",
                body={"segments": [{"segment_id": "{{segment_id}}", "slot_position": 0},
                                   {"start": [11.8724, 47.0581], "end": [11.8800, 47.0700], "slot_position": 1}]},
                test=["var jsonData = pm.response.json();",
                      'pm.test("the report has is_valid, errors and warnings", function () { var r = jsonData.response_data; pm.expect(r).to.have.property("is_valid"); pm.expect(r.errors).to.be.an("array"); pm.expect(r.warnings).to.be.an("array"); });'],
                desc="The same checks as the save, for an editor while the user is still drawing. A saved segment by id; a drawing that is not saved yet by its first and last point."),
        request("Get one route", "GET", "explorer/routes/{{route_id}}", pre=first,
                desc="With the segment rows, the sports of the default segments, the derived sport and difficulty and `classification_differs`. Add `?expand=sport_type,difficulty_level,difficulty_sport,created_by`."),
        request("Route segments", "GET", "explorer/routes/{{route_id}}/segments", pre=first,
                desc="The segment rows in slot order, the default of a slot first, as the route walks them."),
        request("Route geometry", "GET", "explorer/routes/{{route_id}}/geometry", pre=first,
                desc="The map line and the elevation profile of the whole default path, and the alternatives as separate lines."),
        request("Update route", "PATCH", "explorer/routes/{{route_id}}", pre=first,
                body={"summary": "Changed from Postman", "plan_conditions": {"best_months": [6, 7, 8], "permit_required": False}},
                desc="Name, texts, `is_public` (publishing a route also publishes its own segments), sport and difficulty by hand, and plan conditions (only the fields you send)."),
        request("Delete route", "DELETE", "explorer/routes/{{route_id}}", pre=SKIP_DELETES + first, status=[200, 409],
                test=['if (pm.response.code === 200) { pm.environment.unset("route_id"); }'],
                desc="The segments stay. 409 when a journey uses the route."),
    ], "Chains of segments. Test with your GPX file: run `Create segment from a GPX file` (folder segments), then 1. Create route, then 2. Put the segment into the route, then Get one route.")


def profile_folder():
    reg_pre = [
        "// Random letters only",
        "function randomLetters(min, max) {",
        '    const chars = "abcdefghijklmnopqrstuvwxyz";',
        "    const length = Math.floor(Math.random() * (max - min + 1)) + min;",
        '    let result = "";',
        "    for (let i = 0; i < length; i++) {",
        "        result += chars.charAt(Math.floor(Math.random() * chars.length));",
        "    }",
        "    return result;",
        "}",
        "",
        "// Capitalize first letter (for names)",
        "function capitalize(str) {",
        "    return str.charAt(0).toUpperCase() + str.slice(1);",
        "}",
        "",
        "// Random alphanumeric (for unique usernames/emails)",
        "function randomAlphaNum(length) {",
        '    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";',
        '    let result = "";',
        "    for (let i = 0; i < length; i++) {",
        "        result += chars.charAt(Math.floor(Math.random() * chars.length));",
        "    }",
        "    return result;",
        "}",
        "",
        "// Generate values",
        "const firstName  = capitalize(randomLetters(3, 10));",
        "const lastName   = capitalize(randomLetters(3, 12));",
        "const middleName = capitalize(randomLetters(3, 10));",
        "const username   = randomLetters(4, 8) + randomAlphaNum(4);",
        "const email      = `${username}${randomAlphaNum(3)}@gmail.com`;",
        "",
        "// Save to Postman variables",
        'pm.environment.set("random_email", email);',
        'pm.environment.set("random_username", username);',
        'pm.environment.set("random_first_name", firstName);',
        'pm.environment.set("random_last_name", lastName);',
        'pm.environment.set("random_middle_name", middleName);',
    ]
    token_test = [
        "pm.test(\"Update access_token variable\", function () {",
        "    // Collect token from API response:",
        "    var jsonData = pm.response.json();",
        "    var accessTokenValue = jsonData.response_data.access_token;",
        "",
        "    // Set the environment variable:",
        f'    pm.environment.set("{ARGS.token_var}", accessTokenValue);',
        "});",
    ]

    token_test_if_ok = [
        "if (pm.response.code === 200) {",
        "    var jsonData = pm.response.json();",
        f'    pm.environment.set("{ARGS.token_var}", jsonData.response_data.access_token);',
        "}",
    ]

    def login(who):
        return request(
            f"Login {who}", "POST", "profile/auth/login", auth=False,
            body={"email": f"{{{{{who}_email}}}}", "password": f"{{{{{who}_password}}}}"},
            test=token_test,
            desc=f"Logs in as the `{who}` account of the environment and stores the token in `{{{{{ARGS.token_var}}}}}`. All later calls use it.")

    auth = folder("auth", [
        request("Register", "POST", "profile/auth/register", auth=False, status=201, pre=reg_pre,
                body={"email": "{{random_email}}", "password": "{{new_user_password}}", "username": "{{random_username}}",
                      "first_name": "{{random_first_name}}", "last_name": "{{random_last_name}}"},
                test=[
                    'pm.environment.set("registered_email", pm.environment.get("random_email"));',
                    'pm.environment.set("registered_username", pm.environment.get("random_username"));',
                ],
                desc="Creates a user with random data (pre-request script). Saves the e-mail in `registered_email` (the random_* variables change on the next run). Does not change `access_token`; use Login (registered user)."),
        login("guest"), login("viewer"), login("editor"),
        request("Login registered user", "POST", "profile/auth/login", auth=False, status=[200, 401, 403],
                body={"email": "{{registered_email}}", "password": "{{new_user_password}}"}, test=token_test_if_ok,
                desc="Logs in as the user made by Register (needs `registered_email`). Answers 401 or 403 when the account is not active yet; an administrator can activate it (profile/users, Activate user). The token is only saved on success."),
        login("admin"),
        request("Refresh token", "POST", "profile/auth/refresh", test=token_test,
                desc="Returns a new token for the current one (the old one stops working)."),
        request("Logout", "POST", "profile/auth/logout",
                test=[
                    "// The token is dead now. Log in as admin again so that the next call works.",
                    "pm.sendRequest({",
                    '    url: pm.variables.replaceIn("' + ARGS.scheme + '://' + ARGS.host_ref + ':' + ARGS.port_ref + '/' + ARGS.api_var_ref + '/profile/auth/login"),',
                    '    method: "POST",',
                    '    header: { "Content-Type": "application/json" },',
                    '    body: { mode: "raw", raw: JSON.stringify({ email: pm.environment.get("admin_email"), password: pm.environment.get("admin_password") }) }',
                    "}, function (err, res) {",
                    "    if (!err && res.code === 200) {",
                    f'        pm.environment.set("{ARGS.token_var}", res.json().response_data.access_token);',
                    "    }",
                    "});",
                ],
                desc="Blacklists the current token (the old token is dead afterwards). The test script then logs in as admin again, so the next call works."),
    ], "Run one Login first. Order for a full run: Register, the other logins, Login admin last.")

    users = folder("users", [
        request("List users", "GET", "profile/users/", desc="Administrator only.",
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                    'var wanted = pm.environment.get("registered_email");',
                    "var found = jsonData.response_data.find(function (u) { return u.email === wanted; });",
                    'if (found) { pm.environment.set("registered_user_id", found.id); }',
                ]),
        request("Get me", "GET", "profile/users/me"),
        request("Update me", "PUT", "profile/users/me", body={"first_name": "Postman", "height_cm": 180}),
        request("Get one user", "GET", "profile/users/{{registered_user_id}}",
                desc="Administrator only. Uses `registered_user_id`, found by List users (the account made by Register)."),
        request("Activate user", "PUT", "profile/users/{{registered_user_id}}/activate", desc="Administrator only."),
        request("Deactivate user", "PUT", "profile/users/{{registered_user_id}}/deactivate", desc="Administrator only."),
        request("Change group", "PUT", "profile/users/{{registered_user_id}}/group", body={"user_group": "viewer"},
                desc="Administrator only. Groups: administrator, editor, viewer, guest."),
    ])

    policy_pre = [
        "// A policy needs a resource type. Make a helper one the first time (kept in policy_resource_type_id, deleted by the Cleanup folder).",
        'if (!pm.environment.get("policy_resource_type_id")) {',
        "    pm.sendRequest({",
        f'        url: pm.variables.replaceIn("{ARGS.scheme}://{ARGS.host_ref}:{ARGS.port_ref}/{ARGS.api_var_ref}/core/resource-types"),',
        '        method: "POST",',
        f'        header: {{ "Content-Type": "application/json", Authorization: "Bearer " + pm.environment.get("{ARGS.token_var}") }},',
        '        body: { mode: "raw", raw: JSON.stringify({ key: "pm_" + Math.random().toString(36).slice(2, 12), name: "Postman helper", color: "#607D8B", icon: "lock" }) }',
        "    }, function (err, res) {",
        "        if (!err && res.code === 201) {",
        '            pm.environment.set("policy_resource_type_id", res.json().response_data.id);',
        "        }",
        "    });",
        "}",
    ]
    policies = crud_folder(
        "profile", "access-policies", "access policy", "access_policy_id",
        {"user_group": "guest", "resource_type_id": "{{policy_resource_type_id}}", "action": "read", "scope": "own"},
        {"scope": "all"}, create_pre=policy_pre,
        create_desc="Creates a policy (group guest, action read, scope own) on a helper resource type that the pre-request script makes (so no real policy is touched). Saves the id in `access_policy_id`. Only the four real groups are accepted: administrator, editor, viewer, guest (another name gives a 500).")
    return folder("profile", [auth, users, policies], "Accounts, login and access policies.")


def management_folder():
    log_list_test = [
        "var jsonData = pm.response.json();",
        'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
        "if (jsonData.response_data.length) { pm.environment.set(\"log_id\", jsonData.response_data[0].id); }",
        "if (jsonData.response_data.length > 1) { pm.environment.set(\"log_id_2\", jsonData.response_data[1].id); }",
    ]
    FIRST_ID_LISTS.append(("management/event-log", "log_id"))
    log_first = first_id_pre("management/event-log", "log_id", second="log_id_2")
    event_log = folder("event-log", [
        request("List event log", "GET", "management/event-log", test=log_list_test,
                enabled_query={"limit": "20"}, desc="Administrator only. Change history of objects. Saves the first two ids in `log_id` and `log_id_2`."),
        request("List entity types", "GET", "management/event-log/entity-types"),
        request("Get one event", "GET", "management/event-log/{{log_id}}", pre=log_first),
        request("Compare two events", "GET", "management/event-log/{{log_id}}/compare/{{log_id_2}}", pre=log_first, status=[200, 400],
                desc="Compares two entries of the same object. 400 when `log_id` and `log_id_2` (the first two rows of the list) belong to different objects."),
    ])
    FIRST_ID_LISTS.append(("management/settings", "setting_key"))
    setting_first = first_id_pre("management/settings", "setting_key", extra=[("setting_value", "value")])
    settings = folder("settings", [
        request("List settings", "GET", "management/settings",
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                    "if (jsonData.response_data.length) {",
                    '    pm.environment.set("setting_key", jsonData.response_data[0].key);',
                    '    pm.environment.set("setting_value", JSON.stringify(jsonData.response_data[0].value));',
                    "}",
                ], desc="Administrator only. Runtime settings. Saves the first key and its value in `setting_key` and `setting_value`."),
        request("Get one setting", "GET", "management/settings/{{setting_key}}", pre=setting_first),
        request("Update setting", "PATCH", "management/settings/{{setting_key}}", body='{\n    "value": {{setting_value}}\n}', pre=setting_first,
                desc="Sends back the value that List settings saved (no change). Edit the body to change a setting."),
        request("Reset setting", "POST", "management/settings/{{setting_key}}/reset", pre=setting_first, desc="Puts the default value back."),
    ])
    FIRST_ID_LISTS.append(("management/my-jobs", "job_id"))
    job_first = first_id_pre("management/my-jobs", "job_id")
    my_jobs = folder("my-jobs", [
        request("List my jobs", "GET", "management/my-jobs", enabled_query={"limit": "20"},
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                    'if (!pm.environment.get("job_id") && jsonData.response_data.length) { pm.environment.set("job_id", jsonData.response_data[0].id); }',
                ], desc="Background jobs started by you (GPX processing, rescans)."),
        request("Get one of my jobs", "GET", "management/my-jobs/{{job_id}}", pre=job_first, desc="Uses `job_id` (set by an upload or rescan, or by List my jobs)."),
    ])
    admin_jobs = folder("jobs", [
        request("List all jobs", "GET", "management/jobs",
                enabled_query={"limit": "20"},
                desc="Administrator only. Filters (status, kind, user_id, created_from, created_to, ...) and sort are listed and switched off."),
        request("Job statistics", "GET", "management/jobs/stats", desc="Administrator only."),
        request("Get any job", "GET", "management/jobs/{{job_id}}", pre=job_first, desc="Administrator only."),
    ])
    broadcast = folder("broadcast", [
        request("Send notice", "POST", "management/broadcast", body={"level": "info", "text": "Notice from Postman"},
                desc="Administrator only. Sends a notice to every connected WebSocket."),
    ])
    celery = folder("celery", [
        request("Celery status", "GET", "management/celery/status", desc="Administrator only."),
        request("Celery workers", "GET", "management/celery/workers"),
        request("Registered tasks", "GET", "management/celery/tasks/registered"),
        request("Active tasks", "GET", "management/celery/tasks/active"),
        request("Task detail", "GET", "management/celery/tasks/{{job_id}}", status=[200, 404], pre=job_first,
                desc="A job id is also its Celery task id. Needs `job_id` (set by an upload or rescan, or by List my jobs); answers 404 when the task is unknown."),
        request("Beat schedule", "GET", "management/celery/beat"),
    ])
    ws = folder("ws", [
        request("WebSocket ticket", "POST", "management/ws/ticket",
                test=["var jsonData = pm.response.json();", 'pm.environment.set("ws_ticket", jsonData.response_data.ticket);'],
                desc=("One-time ticket (30 s) for a WebSocket. Saves `ws_ticket`. Open a new WebSocket request in Postman with "
                      f"`ws://{ARGS.host_ref}:{ARGS.port_ref}/{ARGS.api_var_ref}/management/ws?ticket={{{{ws_ticket}}}}` "
                      f"or, for one job, `.../management/ws/jobs/{{{{job_id}}}}?ticket={{{{ws_ticket}}}}`. (WebSocket requests are not part of an importable collection.)")),
    ])
    return folder("management", [event_log, settings, my_jobs, admin_jobs, broadcast, celery, ws],
                  "Administration and background jobs. Most calls are administrator only; my-jobs and ws are for every logged-in user.")


def cleanup_folder():
    order = [  # dependency-safe order: things that point at others first
        ("DELETE", "profile/access-policies/{{access_policy_id}}", "access_policy_id"),
        ("DELETE", "core/resource-types/{{policy_resource_type_id}}", "policy_resource_type_id"),
        ("DELETE", "compendium/poi-regions/{{poi_region_id}}", "poi_region_id"),
        ("DELETE", "compendium/cards/{{card_id}}", "card_id"),
        ("DELETE", "compendium/posts/{{post_id}}", "post_id"),
        ("DELETE", "compendium/pois/{{poi_id}}", "poi_id"),
        ("PHOTOS", "", ""),     # after the cards, posts and POIs that hold a photo as their main photo
        ("DELETE", "assets/photos/{{photo_id}}", "photo_id"),
        ("DELETE", "compendium/regions/{{region_id}}", "region_id"),
        ("DELETE", "compendium/countries/{{country_id}}", "country_id"),
        ("DELETE", "explorer/gear/{{gear_id}}", "gear_id"),
        ("DELETE", "explorer/routes/{{route_id}}", "route_id"),
        ("DELETE", "explorer/segments/{{segment_id}}", "segment_id"),
        ("DELETE", "core/resource-types/{{resource_type_id}}", "resource_type_id"),
    ]
    refs = ["companies/{{company_id}}", "gear-types/{{gear_type_id}}", "achievement-categories/{{achievement_category_id}}",
            "achievement-scopes/{{achievement_scope_id}}", "achievement-types/{{achievement_type_id}}",
            "compendium-types/{{compendium_type_id}}", "difficulty-levels/{{difficulty_level_id}}",
            "difficulty-sports/{{difficulty_sport_id}}", "point-reasons/{{point_reason_id}}", "post-types/{{post_type_id}}",
            "rarities/{{rarity_id}}", "region-types/{{region_type_id}}", "schedule-statuses/{{schedule_status_id}}",
            "snow-conditions/{{snow_condition_id}}", "sport-types/{{sport_type_id}}", "trail-conditions/{{trail_condition_id}}",
            "visibilities/{{visibility_id}}", "waypoint-types/{{waypoint_type_id}}", "weather-conditions/{{weather_condition_id}}"]
    for r in refs:
        order.append(("DELETE", f"core/{r}", re.search(r"\{\{(\w+)\}\}", r).group(1)))
    order.append(("ICONS", "", ""))     # last: countries, regions, reference values and resource types hold icons (a used icon cannot be deleted)
    order.append(("DELETE", "assets/icons/{{icon_id}}", "icon_id"))
    items = [
        request("Delete the routes this collection made", "GET", "explorer/routes", pre=delete_all_pre("created_route_ids", "explorer/routes"),
                desc="Deletes every route whose id was kept by a Create call of this collection (variable `created_route_ids`)."),
        request("Delete the segments this collection made", "GET", "explorer/segments", pre=delete_all_pre("created_segment_ids", "explorer/segments"),
                desc="Deletes every segment that a Create call or a route save of this collection made (variable `created_segment_ids`), after the routes are gone."),
    ]
    for method, path, var in order:
        if method == "PHOTOS":
            items.append(request("Delete the photos this collection made", "GET", "assets/photos",
                                 pre=delete_all_pre("created_photo_ids", "assets/photos"),
                                 desc="Deletes every photo that Upload photo of this collection made (variable `created_photo_ids`), after the cards, posts and POIs that used them are gone "
                                      "(a photo cannot be deleted while it is the main photo of something). GPX files are not removed here: a track keeps its file."))
            continue
        if method == "ICONS":
            items.append(request("Delete the icons this collection made", "GET", "assets/icons",
                                 pre=delete_all_pre("created_icon_ids", "assets/icons"),
                                 desc="Deletes every icon that Upload icon of this collection made (variable `created_icon_ids`), after the countries, regions, reference values and resource types "
                                      "that used them are gone (an icon cannot be deleted while something uses it). Icons that the collection did not make (the flags) stay."))
            continue
        label = path.split("/")[0] + " / " + path.split("/")[1]
        it = request(f"Delete {label}", method, path, status=[200, 204, 404, 409, 422],
                     test=[f'pm.environment.unset("{var}");'])
        items.append(it)
    return folder("Cleanup (optional)", items,
                  "Deletes the records the Create calls made, in an order that respects the links between them (links first, then what they point at). "
                  "Run this folder with the Collection Runner after a full run. Answers 404, 409 and 422 are accepted, so it can be run twice.")


def collect_folder():
    # One request that reads the first row of every list (limit=1) and saves its id in the variable that the Get one, Update
    # and Delete requests of that model use. Built after all other folders, because they fill FIRST_ID_LISTS.
    pairs = ",\n".join(f'    ["{path}", "{var}"]' for path, var in FIRST_ID_LISTS)
    lines = [
        "// Reads the first row of every list and saves its id in the variable of that model (company_id, poi_id, track_id, ...).",
        "// By default an id that is already set (made by a Create call) is kept; set the variable collect_overwrite to true to replace them.",
        'var overwrite = pm.environment.get("collect_overwrite") === "true";',
        f'var token = pm.environment.get("{ARGS.token_var}");',
        f'var base = pm.variables.replaceIn("{api_url("")}");',
        "var lists = [",
        pairs,
        "];",
        "var saved = [], kept = [], empty = [], failed = [];",
        "lists.forEach(function (item) {",
        "    var path = item[0], variable = item[1];",
        '    if (!overwrite && pm.environment.get(variable)) { kept.push(variable); return; }',
        '    pm.sendRequest({ url: base + path + "?limit=" + (variable === "log_id" ? 2 : 1), method: "GET", header: { Authorization: "Bearer " + token } }, function (err, res) {',
        "        if (err || res.code !== 200) { failed.push(path + " + '" (" + (err ? "no answer" : res.code) + ")"' + "); return; }",
        "        var rows = res.json().response_data;",
        "        if (!rows || !rows.length) { empty.push(path); return; }",
        '        pm.environment.set(variable, variable === "setting_key" ? rows[0].key : rows[0].id);',
        '        if (variable === "setting_key") { pm.environment.set("setting_value", JSON.stringify(rows[0].value)); }',
        '        if (variable === "log_id" && rows.length > 1) { pm.environment.set("log_id_2", rows[1].id); }',
        "        saved.push(variable);",
        "    });",
        "});",
        "setTimeout(function () {",
        '    console.log("saved: " + saved.join(", ") + "\\nkept (already set): " + kept.join(", ") + "\\nlist is empty: " + empty.join(", ") + "\\nfailed: " + failed.join(", "));',
        "}, 3000);",
        'pm.test("Every list answered (an empty list is fine, a failed one is not)", function () { pm.expect(failed, failed.join("; ")).to.have.lengthOf(0); });',
    ]
    return folder("Collect first IDs (optional)", [
        request("Collect first IDs (all lists)", "GET", "../health", auth=False, test=lines,
                desc=("Run it once and every Get one, Update and Delete request can run alone: it reads the first row of each list "
                      "(core, compendium, explorer, management, access policies) and saves its id in the variable that the requests of that model use "
                      "(`company_id`, `poi_id`, `track_id`, `log_id`, `setting_key`, ...). It needs a login (`access_token`). "
                      "An id that a Create call already saved is kept; set `collect_overwrite` to `true` in the environment to replace all of them. "
                      "Careful: with the ids of real rows in the variables, a Delete request deletes a real row (Delete requests with an empty variable do the same on their own)."))],
        "Fills the id variables from the first row of every list, so single requests can run without Create first. The List requests and the Get one, Update and Delete requests of every model do the same for their own model.")


def health_folder():
    return folder("health", [request("Health", "GET", "../health", auth=False,
                                      test=['pm.test("Database and Redis are up", function () { var d = pm.response.json().response_data; pm.expect(d.status).to.eql("ok"); pm.expect(d.redis_connected).to.eql(true); });'],
                                      desc="Outside /api/v1: `/health`. No login needed.")])


# ------------------------------------------------------------------ collection

COLLECTION_PRE = [
    "// Random values for the Create calls (unique per call)",
    "function letters(n) { var c = 'abcdefghijklmnopqrstuvwxyz', r = ''; for (var i = 0; i < n; i++) { r += c.charAt(Math.floor(Math.random() * c.length)); } return r; }",
    "function alnum(n) { var c = 'abcdefghijklmnopqrstuvwxyz0123456789', r = ''; for (var i = 0; i < n; i++) { r += c.charAt(Math.floor(Math.random() * c.length)); } return r; }",
    "var name = letters(1).toUpperCase() + letters(5) + alnum(4);",
    'pm.environment.set("random_name", "Pm " + name);',
    'pm.environment.set("random_key", "pm_" + alnum(10));',
    '// ISO country codes starting with X are reserved for private use, so they never clash with real data',
    'pm.environment.set("random_iso_code", "X" + letters(1).toUpperCase());',
]

COLLECTION_TEST = [
    "// The API sends a fresh token in the X-Access-Token header when the current one is half used up. Keep using the newest one.",
    'var rotated = pm.response.headers.get("X-Access-Token");',
    "if (rotated) {",
    f'    pm.environment.set("{{TOKEN}}", rotated);',
    "}",
]


def build_collection():
    description = f"""Alpen Wege API (generated by build_postman.py from the API's OpenAPI description).

**Use:** import this collection and `Alpen API local.postman_environment.json`, select the environment, run **profile / auth / Login admin** once, then any call. Tokens last only a few minutes; the collection keeps the newest one automatically (header `X-Access-Token`). If a call answers 401, log in again.

**URL:** `{ARGS.scheme}://{ARGS.host_ref}:{ARGS.port_ref}/{ARGS.api_var_ref}/<app>/<resource>`. Folders: one per app (core, assets, compendium, explorer, profile, management), one per model inside.

**Photos and GPX files (assets):** run **assets / photos / Upload photo** once. It saves `photo_id`, and from then on the Create and Update calls of cards, POIs and posts send `"main_photo_id": "{{{{photo_id}}}}"`, so they all use that photo (an empty `photo_id` is filled with the first photo of the list; when there is no photo at all the field is left out). **explorer / tracks / Upload track** saves `gpx_id`, the stored file shown in assets / gpx. The upload requests point at `{SAMPLE_PHOTO}` and `{SAMPLE_GPX}`: put both files in the Postman working directory (Settings, General, Working directory) or choose a file in the body once.

**Icons and flags (assets):** run **assets / icons / Upload icon** once (admin). It saves `icon_id` and `icon_key`, and from then on the Create and Update calls of the 19 reference tables, resource types, countries and regions send `"icon_id": "{{{{icon_id}}}}"`, so they all use that icon (an empty `icon_id` is filled with the first icon of the list, for example a flag; when there is no icon at all the field is left out). `assets / icons / Icon file ...` shows the picture (SVG, PNG, by id or by key). **All icons at once:** `Upload icons CSV (dry run)`, then `Upload icons CSV (import all)` (the CSV `{SAMPLE_ICONS_CSV}` carries the graphics of all 438 icons; with `link=true` countries and regions get their flag), and `Link rows to icons by key` for later. Reference values and resource types need an icon: on an empty database upload one before the core folder. The upload requests point at `{SAMPLE_ICON}` and `{SAMPLE_ICONS_CSV}`: put both in the Postman working directory too.

**Variables:** `{ARGS.host_var}`, `{ARGS.port_var}`, `{ARGS.api_var}` (= `api/v1`), `<who>_email` / `<who>_password` for admin, editor, viewer, guest, `new_user_password`, and `{ARGS.token_var}`. Create calls save ids in variables such as `country_id`, `region_id`, `poi_id`; the next calls use them. **Run a single request alone:** run **Collect first IDs (optional) / Collect first IDs (all lists)** once (after a login), or any List request: they save the id of the first row in the variable of each model. Get one, Update and Delete requests also fill an empty variable themselves from the first row of their list. Careful: a Delete request with such an id deletes a real row. For a full run with the Collection Runner: set `skip_deletes` to `true` (the Delete calls of the model folders are skipped), run the app folders in the order shown, then run the folder **Cleanup (optional)**, which deletes everything in the right order. The Upload CSV and Upload track calls need a file chosen in their body.

**Not covered:** WebSocket requests (see management / ws for the ticket and the URLs)."""
    items = [
        health_folder(),
        profile_folder(),
        core_folder(),
        # Order for a full Runner run: explorer (Upload track saves gpx_id) before assets (the GPX files exist now, Upload photo
        # saves photo_id) before compendium (cards, POIs and posts use photo_id). Nothing in explorer needs compendium data.
        explorer_folder(),
        assets_folder(),
        compendium_folder(),
        management_folder(),
        cleanup_folder(),
    ]
    items.insert(2, collect_folder())    # after health and profile (the login is in profile / auth)
    return {
        "info": {
            "_postman_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "alpen-wege-api-collection")),
            "name": "Alpen API",
            "description": description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": f"{{{{{ARGS.token_var}}}}}", "type": "string"}]},
        "event": [
            event("prerequest", COLLECTION_PRE),
            event("test", [l.replace("{TOKEN}", ARGS.token_var) for l in COLLECTION_TEST]),
        ],
        "item": items,
    }


def build_environment():
    def var(key, value="", secret=False):
        return {"key": key, "value": value, "type": "secret" if secret else "default", "enabled": True}
    values = [
        var(ARGS.host_var, "localhost"), var(ARGS.port_var, "8000"), var(ARGS.api_var, "api/v1"),
        var("admin_email", "admin@alpenwege.dev"), var("admin_password", "!Password@5005", True),
        var("editor_email", "editor@alpenwege.dev"), var("editor_password", "!Password@5005", True),
        var("viewer_email", "viewer@alpenwege.dev"), var("viewer_password", "!Password@5005", True),
        var("guest_email", "guest@alpenwege.dev"), var("guest_password", "!Password@5005", True),
        var("new_user_password", "!Password@5005", True),
        var("skip_deletes", "false"),
        var("collect_overwrite", "false"),
        var(ARGS.token_var, "", True),
    ]
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "alpen-wege-api-environment")),
        "name": "Alpen API local",
        "values": values,
        "_postman_variable_scope": "environment",
    }


# ------------------------------------------------------------------ coverage check

BODY_FIELDS: dict = {}  # key_of(method, path) -> names of the JSON body fields the API accepts there


def _schema_fields(spec, schema, seen=()):
    if not schema:
        return set()
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        if name in seen:
            return set()
        return _schema_fields(spec, spec["components"]["schemas"].get(name), seen + (name,))
    fields = set(schema.get("properties", {}))
    for part in schema.get("allOf", []):
        fields |= _schema_fields(spec, part, seen)
    return fields


def check_asset_links():
    """The photo mechanism cannot be forgotten: for every request body the API accepts with a field of ASSET_LINKS, at least one
    request of the collection sends that field, and every request that sends it uses the variable (or null, to clear the link)."""
    problems = []
    for key, fields in sorted(BODY_FIELDS.items()):
        for field, var in ASSET_LINKS.items():
            if field not in fields:
                continue
            bodies = BODIES.get(key, [])
            if not any(f'"{field}": "{{{{{var}}}}}"' in b for b in bodies):
                problems.append(f"{key}: the API accepts `{field}` but no request body sends \"{field}\": \"{{{{{var}}}}}\"")
    for key, bodies in sorted(BODIES.items()):
        for b in bodies:
            for field, var in ASSET_LINKS.items():
                m = re.search(rf'"{field}":\s*("(?:[^"\\]|\\.)*"|null|[^,\s}}]+)', b)
                if m and m.group(1) not in (f'"{{{{{var}}}}}"', "null"):
                    problems.append(f"{key}: `{field}` is {m.group(1)}, expected \"{{{{{var}}}}}\" or null")
    return problems


def check_body_format():
    """Every raw JSON body is written the same way (pretty() = 4 spaces, one member per line). A placeholder {{x}} is replaced by a
    dummy value and the body must equal json.dumps(indent=4) of what it parses to."""
    problems = []
    for key, bodies in sorted(BODIES.items()):
        for b in bodies:
            probe = re.sub(r"\{\{\w+\}\}", "0", re.sub(r'"\{\{\w+\}\}"', '"x"', b))
            try:
                again = json.dumps(json.loads(probe), indent=4, ensure_ascii=False)
            except ValueError as e:
                problems.append(f"{key}: the body is not valid JSON ({e})")
                continue
            if again != probe:
                problems.append(f"{key}: the body is not formatted with 4 spaces, one member per line")
    return problems


def load_openapi(path):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    ops = {}
    for p, methods in spec["paths"].items():
        rel = p
        if rel.startswith("/api/v1/"):
            rel = rel[len("/api/v1/"):]
        else:
            rel = ".." + rel
        for m, o in methods.items():
            if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                k = key_of(m, rel)
                ops[k] = o
                json_body = ((o.get("requestBody") or {}).get("content") or {}).get("application/json")
                if json_body:
                    BODY_FIELDS[k] = _schema_fields(spec, json_body.get("schema"))
                QUERY_PARAMS[k] = [
                    (prm["name"], (prm.get("description") or ("required" if prm.get("required") else "optional")))
                    for prm in o.get("parameters", []) if prm["in"] == "query"
                ]
    return ops


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--openapi", required=True, help="file saved from <host>/openapi.json")
    ap.add_argument("--out", default=".")
    ap.add_argument("--scheme", default="http")
    ap.add_argument("--host-var", default="hostname")
    ap.add_argument("--port-var", default="port")
    ap.add_argument("--api-var", default="api_path")
    ap.add_argument("--token-var", default="access_token")
    ARGS = ap.parse_args()
    ARGS.host_ref = "{{" + ARGS.host_var + "}}"
    ARGS.port_ref = "{{" + ARGS.port_var + "}}"
    ARGS.api_var_ref = "{{" + ARGS.api_var + "}}"

    ops = load_openapi(ARGS.openapi)
    collection = build_collection()
    built = {key_of(m, p) for m, p in REQUESTS}
    missing = sorted(set(ops) - built)
    extra = sorted(built - set(ops))
    if missing or extra:
        print("COVERAGE PROBLEM")
        for k in missing:
            print("  no request for", k)
        for k in extra:
            print("  request without a route in the API:", k)
        sys.exit(1)
    link_problems = check_asset_links()
    format_problems = check_body_format()
    if link_problems or format_problems:
        print("ASSET LINK / BODY FORMAT PROBLEM")
        for p in link_problems + format_problems:
            print("  ", p)
        sys.exit(1)

    out = Path(ARGS.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "Alpen API.postman_collection.json").write_text(json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "Alpen API local.postman_environment.json").write_text(json.dumps(build_environment(), indent=2, ensure_ascii=False), encoding="utf-8")

    def count(items):
        n = 0
        for i in items:
            n += count(i["item"]) if "item" in i else 1
        return n
    print(f"{len(ops)} API routes covered, {count(collection['item'])} requests written to {out}")


if __name__ == "__main__":
    main()
