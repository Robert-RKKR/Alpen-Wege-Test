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

Structure: one folder per app (core, compendium, explorer, profile, management), one folder per model
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


def crud_folder(app, slug, label, var, create_body, update_body, *, needs="", extras=None, csv=True,
                list_extra_test=None, create_pre=None, create_desc=""):
    base = f"{app}/{slug}"
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
        request(f"Get one {label}", "GET", f"{base}/{{{{{var}}}}}", desc=f"Uses `{{{{{var}}}}}` (set by Create or List)."),
        request(f"Update {label}", "PATCH", f"{base}/{{{{{var}}}}}", body=update_body,
                desc="Only the fields in the body change."),
    ]
    items += (extras or [])
    if csv:
        items.append(csv_request(base, label))
    items.append(request(f"Delete {label}", "DELETE", f"{base}/{{{{{var}}}}}", pre=SKIP_DELETES,
                         test=[f'pm.environment.unset("{var}");'],
                         desc=f"Deletes `{{{{{var}}}}}` and clears the variable. Records that other records point at cannot be deleted until those are deleted."))
    return folder(slug, items)


SKIP_DELETES = [
    "// Collection Runner: set the variable skip_deletes to true to keep all records until the folder Cleanup (optional) runs.",
    'if (pm.environment.get("skip_deletes") === "true") { pm.execution.skipRequest(); }',
]


def ref_folder(slug, label, var, *, factor=True, extra_fields=None, name_required=False):
    body = {"name": "{{random_name}}", "name_de": "{{random_name}}", "color": "#2196F3", "icon": "star"}
    if factor:
        body["point_factor"] = 1.0
    body.update(extra_fields or {})
    upd = {"color": "#FF9800"}
    if factor:
        upd["point_factor"] = 2.0
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
    poi_rescan = request("Rescan POI", "POST", "compendium/pois/{{poi_id}}/rescan", status=202,
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
    card_rescan = request("Rescan card", "POST", "compendium/cards/{{card_id}}/rescan", status=202,
                          test=[
                              "var jsonData = pm.response.json();",
                              'pm.environment.set("job_id", jsonData.response_data.job_id);',
                          ],
                          desc="Starts a background job for this card. Saves `job_id`.")
    card = crud_folder(
        "compendium", "cards", "card", "card_id",
        {"name": "{{random_name}}", "poi_id": "{{poi_id}}"}, {"name": "{{random_name}} renamed"},
        needs="`poi_id` (compendium/pois)", extras=[card_rescan])
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


def explorer_folder():
    gear = crud_folder(
        "explorer", "gear", "gear", "gear_id",
        {"name": "{{random_name}}", "company_id": "{{company_id}}", "gear_type_id": "{{gear_type_id}}",
         "model": "Test model", "weight_g": 500},
        {"weight_g": 450}, needs="`company_id` (core/companies), `gear_type_id` (core/gear-types)")
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
        request("Get one track", "GET", "explorer/tracks/{{track_id}}"),
        request("Track geometry", "GET", "explorer/tracks/{{track_id}}/geometry", status=[200, 404],
                desc="404 until the processing job has finished."),
        request("Track performance", "GET", "explorer/tracks/{{track_id}}/performance", status=[200, 404],
                desc="404 when the file has no timestamps or the job is not finished."),
        request("Update track", "PATCH", "explorer/tracks/{{track_id}}", body={"name": "Renamed {{random_name}}", "is_public": False}),
        request("Reprocess track", "POST", "explorer/tracks/{{track_id}}/reprocess", status=[202, 409],
                desc="Only tracks with processing_status `failed` can be reprocessed (409 otherwise).",
                test=["var jsonData = pm.response.json();",
                      'if (pm.response.code === 202) { pm.environment.set("job_id", jsonData.response_data.job_id); }']),
        request("Archive track (DELETE)", "DELETE", "explorer/tracks/{{track_id}}",
                desc="Archives the track (it is not deleted). Restore brings it back."),
        request("Restore track", "POST", "explorer/tracks/{{track_id}}/restore"),
    ])
    return folder("explorer", [gear, tracks], "User activity data: gear and tracks.")


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
    event_log = folder("event-log", [
        request("List event log", "GET", "management/event-log", test=log_list_test,
                enabled_query={"limit": "20"}, desc="Administrator only. Change history of objects. Saves the first two ids in `log_id` and `log_id_2`."),
        request("List entity types", "GET", "management/event-log/entity-types"),
        request("Get one event", "GET", "management/event-log/{{log_id}}"),
        request("Compare two events", "GET", "management/event-log/{{log_id}}/compare/{{log_id_2}}"),
    ])
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
        request("Get one setting", "GET", "management/settings/{{setting_key}}"),
        request("Update setting", "PATCH", "management/settings/{{setting_key}}", body='{"value": {{setting_value}}}',
                desc="Sends back the value that List settings saved (no change). Edit the body to change a setting."),
        request("Reset setting", "POST", "management/settings/{{setting_key}}/reset", desc="Puts the default value back."),
    ])
    my_jobs = folder("my-jobs", [
        request("List my jobs", "GET", "management/my-jobs", enabled_query={"limit": "20"},
                test=[
                    "var jsonData = pm.response.json();",
                    'pm.test("Response has a list in response_data", function () { pm.expect(jsonData.response_data).to.be.an("array"); });',
                    'if (!pm.environment.get("job_id") && jsonData.response_data.length) { pm.environment.set("job_id", jsonData.response_data[0].id); }',
                ], desc="Background jobs started by you (GPX processing, rescans)."),
        request("Get one of my jobs", "GET", "management/my-jobs/{{job_id}}", desc="Uses `job_id` (set by an upload or rescan, or by List my jobs)."),
    ])
    admin_jobs = folder("jobs", [
        request("List all jobs", "GET", "management/jobs",
                enabled_query={"created_from": "2020-01-01T00:00:00", "created_to": "2099-01-01T00:00:00", "limit": "20"},
                desc="Administrator only. `created_from` and `created_to` are switched on because the API answers 500 when either is missing (known bug, not fixed yet). Switch them off after the fix."),
        request("Job statistics", "GET", "management/jobs/stats", desc="Administrator only."),
        request("Get any job", "GET", "management/jobs/{{job_id}}", desc="Administrator only."),
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
        request("Task detail", "GET", "management/celery/tasks/{{job_id}}", desc="A job id is also its Celery task id."),
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
        ("DELETE", "compendium/regions/{{region_id}}", "region_id"),
        ("DELETE", "compendium/countries/{{country_id}}", "country_id"),
        ("DELETE", "explorer/gear/{{gear_id}}", "gear_id"),
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
    items = []
    for method, path, var in order:
        label = path.split("/")[0] + " / " + path.split("/")[1]
        it = request(f"Delete {label}", method, path, status=[200, 204, 404, 409, 422],
                     test=[f'pm.environment.unset("{var}");'])
        items.append(it)
    return folder("Cleanup (optional)", items,
                  "Deletes the records the Create calls made, in an order that respects the links between them (links first, then what they point at). "
                  "Run this folder with the Collection Runner after a full run. Answers 404, 409 and 422 are accepted, so it can be run twice.")


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

**URL:** `{ARGS.scheme}://{ARGS.host_ref}:{ARGS.port_ref}/{ARGS.api_var_ref}/<app>/<resource>`. Folders: one per app (core, compendium, explorer, profile, management), one per model inside.

**Variables:** `{ARGS.host_var}`, `{ARGS.port_var}`, `{ARGS.api_var}` (= `api/v1`), `<who>_email` / `<who>_password` for admin, editor, viewer, guest, `new_user_password`, and `{ARGS.token_var}`. Create calls save ids in variables such as `country_id`, `region_id`, `poi_id`; the next calls use them. For a full run with the Collection Runner: set `skip_deletes` to `true` (the Delete calls of the model folders are skipped), run the app folders in the order shown, then run the folder **Cleanup (optional)**, which deletes everything in the right order. The Upload CSV and Upload track calls need a file chosen in their body.

**Not covered:** WebSocket requests (see management / ws for the ticket and the URLs)."""
    items = [
        health_folder(),
        profile_folder(),
        core_folder(),
        compendium_folder(),
        explorer_folder(),
        management_folder(),
        cleanup_folder(),
    ]
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
