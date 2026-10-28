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

Structure: one folder per app (core, compendium, assets, explorer, profile, management), one folder per model
inside. Every model folder has List, Create, Get one, Update, Delete (and Upload CSV or the special
calls where the API has them). Create calls save the new id in a variable (`country_id`, `poi_id`, ...)
that the following calls of that model and the models that depend on it use.
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


def query_for(method: str, path: str, enabled=()):
    out = []
    for name, schema in QUERY_PARAMS.get(key_of(method, path), []):
        q = {"key": name, "value": "", "description": schema}
        if name in enabled:
            q["value"] = enabled[name]
        else:
            q["disabled"] = True
        out.append(q)
    return out


# ------------------------------------------------------------------ request builder

REQUESTS: list = []  # (method, path) of every request built, for the coverage check


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
            auth=True, enabled_query=(), headers=None):
    REQUESTS.append((method, path))
    item = {"name": name}
    events = []
    if pre:
        events.append(event("prerequest", pre))
    t = tests_status(status) + (test or [])
    events.append(event("test", t))
    item["event"] = events
    req = {"method": method, "header": list(headers or []), "url": make_url(path, query_for(method, path, enabled_query))}
    if body is not None:
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = {"mode": "raw", "raw": body if isinstance(body, str) else json.dumps(body, indent=4),
                       "options": {"raw": {"language": "json"}}}
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


def crud_folder(app, slug, label, var, create_body, update_body, *, needs="", extras=None, csv=True,
                list_extra_test=None, create_pre=None, create_desc=""):
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
                test=set_from_response(var), desc=create_desc or f"Creates one record and saves its id in `{{{{{var}}}}}`.{needs_txt}"),
        request(f"Get one {label}", "GET", f"{base}/{{{{{var}}}}}", pre=first,
                desc=f"Uses `{{{{{var}}}}}` (set by Create, List or Collect first IDs; when empty the first row of the list is used)."),
        request(f"Update {label}", "PATCH", f"{base}/{{{{{var}}}}}", body=update_body, pre=first,
                desc="Only the fields in the body change. When `{{" + var + "}}` is empty the first row of the list is changed."),
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
    body = {"name": "{{random_name}}", "name_de": "{{random_name}}", "color": "#2196F3", "icon": "star"}
    if factor:
        body["point_factor"] = 1.0
    if slug in RANKED_TABLES:
        body["rank"] = 3
    body.update(extra_fields or {})
    upd = {"color": "#FF9800"}
    if factor:
        upd["point_factor"] = 2.0
    if slug in RANKED_TABLES:
        upd["rank"] = 4
    return crud_folder("core", slug, label, var, body, upd)


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
        {"key": "{{random_key}}", "name": "{{random_name}}", "color": "#9C27B0", "icon": "lock"},
        {"name": "{{random_name}} renamed"},
        extras=None,
    ))
    return folder("core", items, "Reference data (19 lookup tables) and resource types. Administrator for create, update, delete.")


def compendium_folder():
    country = crud_folder(
        "compendium", "countries", "country", "country_id",
        {"name": "{{random_name}}", "iso_code": "{{random_iso_code}}", "location": POINT, "capital": "Test City"},
        {"capital": "Updated City"})
    region = crud_folder(
        "compendium", "regions", "region", "region_id",
        {"name": "{{random_name}}", "location": POINT, "country_id": "{{country_id}}", "region_type_id": "{{region_type_id}}"},
        {"summary": "Updated summary"}, needs="`country_id` (compendium/countries), `region_type_id` (core/region-types)")
    poi_rescan = request("Rescan POI", "POST", "compendium/pois/{{poi_id}}/rescan", status=202, pre=first_id_pre("compendium/pois", "poi_id"),
                         test=[
                             "var jsonData = pm.response.json();",
                             'pm.environment.set("job_id", jsonData.response_data.job_id);',
                             'pm.test("Location header points to the job", function () { pm.expect(pm.response.headers.get("Location")).to.include("/management/my-jobs/"); });',
                         ],
                         desc="Starts a background job that matches existing visits against this POI. Saves `job_id`; follow it with management/my-jobs.")
    poi = crud_folder(
        "compendium", "pois", "POI", "poi_id",
        {"name": "{{random_name}}", "location": POINT, "compendium_type_id": "{{compendium_type_id}}",
         "main_region_id": "{{region_id}}", "altitude_m": 2000},
        {"altitude_m": 2100}, needs="`compendium_type_id` (core/compendium-types), `region_id` (compendium/regions)",
        extras=[poi_rescan])
    card_rescan = request("Rescan card", "POST", "compendium/cards/{{card_id}}/rescan", status=202, pre=first_id_pre("compendium/cards", "card_id"),
                          test=[
                              "var jsonData = pm.response.json();",
                              'pm.environment.set("job_id", jsonData.response_data.job_id);',
                          ],
                          desc="Starts a background job for this card. Saves `job_id`.")
    card_first = first_id_pre("compendium/cards", "card_id")
    render_note = ("63x88 mm card with 3 mm bleed. `lang`: en, de, pl. When the stored files are out of date the card is drawn now, "
                   "so the answer is always current. Use Send and Download (or `download=true`) to save the file.")
    card_render = [
        request("Card render model (JSON)", "GET", "compendium/cards/{{card_id}}/render", pre=card_first,
                enabled_query={"format": "json", "lang": "en"},
                test=["var jsonData = pm.response.json();",
                      'pm.test("Model has a number and a name", function () { pm.expect(jsonData.response_data).to.have.property("number"); pm.expect(jsonData.response_data).to.have.property("name"); });'],
                desc="Every value printed on the card, already translated: number, name, flags, country, region, type, altitude, rarity, difficulty, photo, description. For your own front end."),
        request("Card image (SVG)", "GET", "compendium/cards/{{card_id}}/render", pre=card_first,
                enabled_query={"format": "svg", "lang": "en"},
                test=['pm.test("Answer is an SVG", function () { pm.expect(pm.response.headers.get("Content-Type")).to.include("image/svg+xml"); });'],
                desc=render_note),
        request("Card image (PNG, 300 dpi)", "GET", "compendium/cards/{{card_id}}/render", pre=card_first,
                enabled_query={"format": "png", "lang": "en"}, desc=render_note),
        request("Card image (JPG, German)", "GET", "compendium/cards/{{card_id}}/render", pre=card_first,
                enabled_query={"format": "jpg", "lang": "de"}, desc=render_note),
        request("Card for print (PDF)", "GET", "compendium/cards/{{card_id}}/render", pre=card_first,
                enabled_query={"format": "pdf", "lang": "en", "download": "true"},
                desc=render_note + " Print at 100 % (not fit to page) and cut along the rounded edge."),
        request("Render card files again", "POST", "compendium/cards/{{card_id}}/render", status=[202, 409], pre=card_first,
                test=["var jsonData = pm.response.json();",
                      'if (pm.response.code === 202) { pm.environment.set("job_id", jsonData.response_data.job_id); }'],
                desc="Starts a job that writes SVG, PNG and PDF in en, de and pl. Saves `job_id`; 409 when a render is already queued or running. Create and Update queue one by themselves."),
    ]
    card = crud_folder(
        "compendium", "cards", "card", "card_id",
        {"poi_id": "{{poi_id}}", "rarity_id": "{{rarity_id}}", "difficulty_sport_id": "{{difficulty_sport_id}}"},
        {"name": "{{random_name}} renamed"},
        needs="`poi_id` (compendium/pois); optional `rarity_id` (core/rarities), `difficulty_sport_id` (core/difficulty-sports)",
        extras=[card_rescan,
                request("Set card photo", "PATCH", "compendium/cards/{{card_id}}", pre=card_first + first_id_pre("assets/photos", "photo_id"),
                        body={"main_photo_id": "{{photo_id}}"},
                        desc=("Makes `{{photo_id}}` (assets / photos / Upload photo) the main photo of the card and queues a new render. "
                              "Same as Update card with only main_photo_id. 422 when the photo does not exist or you may not read it. "
                              "Send null to remove it; the card then shows the photo of its POI."))] + card_render,
        create_desc=("Creates a card and saves its id in `{{card_id}}`. Only `poi_id` is required; `card_number` is assigned when left out. "
                     "Name, description, type, photo, altitude, country and region come from the POI unless set on the card. "
                     "A render job is queued at once. Needs `poi_id`; `rarity_id` and `difficulty_sport_id` are optional (remove them when empty)."))
    post = crud_folder(
        "compendium", "posts", "post", "post_id",
        {"name": "{{random_name}}", "post_type_id": "{{post_type_id}}"}, {"summary": "Updated summary"},
        needs="`post_type_id` (core/post-types)")
    poi_region = crud_folder(
        "compendium", "poi-regions", "POI-region link", "poi_region_id",
        {"poi_id": "{{poi_id}}", "region_id": "{{region_id}}", "slot_position": 2}, {"slot_position": 3},
        needs="`poi_id` (compendium/pois), `region_id` (compendium/regions)")
    return folder("compendium", [country, region, poi, card, post, poi_region],
                  "Geographic and editorial catalog. Order of Create calls: core region-types, compendium-types, post-types, then country, region, POI, card, post, POI-region link.")


def assets_folder():
    FIRST_ID_LISTS.append(("assets/photos", "photo_id"))
    photo_first = first_id_pre("assets/photos", "photo_id")
    photos = folder("photos", [
        request("List photos", "GET", "assets/photos", enabled_query={},
                test=["var jsonData = pm.response.json();",
                      "pm.test(\"Response has a list in response_data\", function () { pm.expect(jsonData.response_data).to.be.an('array'); });",
                      'if (!pm.environment.get("photo_id") && jsonData.response_data.length) { pm.environment.set("photo_id", jsonData.response_data[0].id); }'],
                desc="All photos you may read. Filters: q, created_by, is_public, altitude, taken_from/to, created_from/to, bbox, near + radius_m."),
        request("Upload photo", "POST", "assets/photos", status=201,
                form=[{"key": "file", "type": "file", "src": []},
                      {"key": "name", "value": "{{random_name}}", "type": "text"},
                      {"key": "summary", "value": "Uploaded from Postman", "type": "text", "disabled": True},
                      {"key": "lon", "value": "8.82", "type": "text", "disabled": True},
                      {"key": "lat", "value": "46.99", "type": "text", "disabled": True},
                      {"key": "altitude_m", "value": "2572", "type": "text", "disabled": True},
                      {"key": "is_public", "value": "true", "type": "text"}],
                test=set_from_response("photo_id"),
                desc=("Pick a JPEG, PNG or WebP in the body (key `file`, at most 25 MB). The image is turned upright, shrunk to 2560 px "
                      "and stored without metadata; position, altitude and time come from EXIF unless the form gives them. Saves `photo_id`. "
                      "Put it on a card, POI or post with their Update call: `{\"main_photo_id\": \"{{photo_id}}\"}` "
                      "(compendium / cards / Set card photo).")),
        request("Get one photo", "GET", "assets/photos/{{photo_id}}", pre=photo_first,
                desc="Uses `{{photo_id}}`. `?expand=created_by` adds the uploader."),
        request("Photo file", "GET", "assets/photos/{{photo_id}}/file", pre=photo_first,
                desc="The image itself (Postman shows it in the response)."),
        request("Update photo", "PATCH", "assets/photos/{{photo_id}}", pre=photo_first,
                body={"summary": "Updated summary", "location": POINT, "is_public": True},
                desc="Only the fields in the body change. The image cannot be replaced: upload a new photo."),
        request("Delete photo", "DELETE", "assets/photos/{{photo_id}}", status=[200, 409], pre=SKIP_DELETES + photo_first,
                test=['if (pm.response.code === 200) { pm.environment.unset("photo_id"); }'],
                desc="Deletes the photo and its file. 409 while it is the main photo of a card, POI, post, gear, segment or track."),
    ], "Photos: upload, read, change, delete. A card, POI or post gets its photo through its own Update call (main_photo_id).")
    FIRST_ID_LISTS.append(("assets/gpx", "gpx_id"))
    gpx_first = first_id_pre("assets/gpx", "gpx_id")
    gpx = folder("gpx", [
        request("List GPX files", "GET", "assets/gpx", enabled_query={},
                test=["var jsonData = pm.response.json();",
                      'if (!pm.environment.get("gpx_id") && jsonData.response_data.length) { pm.environment.set("gpx_id", jsonData.response_data[0].id); }'],
                desc="GPX files you may read. A GPX file is created by explorer / tracks / Upload track. Filter `sha256` finds duplicates."),
        request("Get one GPX file", "GET", "assets/gpx/{{gpx_id}}", pre=gpx_first),
        request("Download GPX file", "GET", "assets/gpx/{{gpx_id}}/file", pre=gpx_first),
        request("Update GPX file", "PATCH", "assets/gpx/{{gpx_id}}", pre=gpx_first, body={"summary": "Updated summary"},
                desc="Name, summary and is_public. The file itself cannot be replaced."),
        request("Delete GPX file", "DELETE", "assets/gpx/{{gpx_id}}", status=[200, 409], pre=SKIP_DELETES + gpx_first,
                test=['if (pm.response.code === 200) { pm.environment.unset("gpx_id"); }'],
                desc="Only a file that no track uses (an orphan); 409 otherwise. Delete the track instead."),
    ], "GPX files of tracks: read, download, rename, delete orphans.")
    return folder("assets", [photos, gpx], "Uploaded files: photos and GPX files.")


def explorer_folder():
    gear = crud_folder(
        "explorer", "gear", "gear", "gear_id",
        {"name": "{{random_name}}", "company_id": "{{company_id}}", "gear_type_id": "{{gear_type_id}}",
         "model": "Test model", "weight_g": 500},
        {"weight_g": 450}, needs="`company_id` (core/companies), `gear_type_id` (core/gear-types)")
    FIRST_ID_LISTS.append(("explorer/tracks", "track_id"))
    track_first = first_id_pre("explorer/tracks", "track_id")
    gpx_note = "Pick a .gpx file in the body (key `gpx_file`). `python scripts/make_sample_gpx.py --variant full --out full.gpx` makes one."
    tracks = folder("tracks", [
        request("List tracks", "GET", "explorer/tracks",
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                    'if (!pm.environment.get("track_id") && jsonData.response_data.length) { pm.environment.set("track_id", jsonData.response_data[0].id); }',
                ], desc="Your tracks. Switch on `archived` to see archived ones."),
        request("Upload track (GPX)", "POST", "explorer/tracks", status=202,
                form=[{"key": "name", "value": "Postman track {{random_name}}", "type": "text"},
                      {"key": "gpx_file", "type": "file", "src": []},
                      {"key": "summary", "value": "Uploaded from Postman", "type": "text"},
                      {"key": "is_public", "value": "false", "type": "text"}],
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.environment.set("track_id", jsonData.response_data.id);',
                    'pm.environment.set("job_id", jsonData.response_data.job_id);',
                    'pm.test("Location header points to the job", function () { pm.expect(pm.response.headers.get("Location")).to.include("/management/my-jobs/"); });',
                ], desc=f"Accepts the file and starts processing as a job (202). Saves `track_id` and `job_id`. {gpx_note}"),
        request("Get one track", "GET", "explorer/tracks/{{track_id}}", pre=track_first),
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
    gpx_note = "Pick a .gpx file in the body (key `gpx_file`). Times and heart rate in the file are dropped; the file itself is not kept."
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
                      {"key": "gpx_file", "type": "file", "src": []},
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
        request("Update setting", "PATCH", "management/settings/{{setting_key}}", body='{"value": {{setting_value}}}', pre=setting_first,
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
        ("DELETE", "assets/photos/{{photo_id}}", "photo_id"),
        ("DELETE", "compendium/posts/{{post_id}}", "post_id"),
        ("DELETE", "compendium/pois/{{poi_id}}", "poi_id"),
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
    items = [
        request("Delete the routes this collection made", "GET", "explorer/routes", pre=delete_all_pre("created_route_ids", "explorer/routes"),
                desc="Deletes every route whose id was kept by a Create call of this collection (variable `created_route_ids`)."),
        request("Delete the segments this collection made", "GET", "explorer/segments", pre=delete_all_pre("created_segment_ids", "explorer/segments"),
                desc="Deletes every segment that a Create call or a route save of this collection made (variable `created_segment_ids`), after the routes are gone."),
    ]
    for method, path, var in order:
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

**URL:** `{ARGS.scheme}://{ARGS.host_ref}:{ARGS.port_ref}/{ARGS.api_var_ref}/<app>/<resource>`. Folders: one per app (core, compendium, assets, explorer, profile, management), one per model inside.

**Variables:** `{ARGS.host_var}`, `{ARGS.port_var}`, `{ARGS.api_var}` (= `api/v1`), `<who>_email` / `<who>_password` for admin, editor, viewer, guest, `new_user_password`, and `{ARGS.token_var}`. Create calls save ids in variables such as `country_id`, `region_id`, `poi_id`; the next calls use them. **Run a single request alone:** run **Collect first IDs (optional) / Collect first IDs (all lists)** once (after a login), or any List request: they save the id of the first row in the variable of each model. Get one, Update and Delete requests also fill an empty variable themselves from the first row of their list. Careful: a Delete request with such an id deletes a real row. For a full run with the Collection Runner: set `skip_deletes` to `true` (the Delete calls of the model folders are skipped), run the app folders in the order shown, then run the folder **Cleanup (optional)**, which deletes everything in the right order. The Upload CSV, Upload track and Upload photo calls need a file chosen in their body.

**Not covered:** WebSocket requests (see management / ws for the ticket and the URLs)."""
    items = [
        health_folder(),
        profile_folder(),
        core_folder(),
        compendium_folder(),
        assets_folder(),
        explorer_folder(),
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
