# GET `?expand=` - decisions

Scope: only single-object GET endpoints (`GET .../{id}`). Lists, POST, PATCH and DELETE are not changed. No database change.

Plan: `get_expand_implementation_plan_v2.md` (2026-10-24; v1 is superseded). Tools and tests: `expand_tools/`. This file is the short list of decisions; the plan has the details and what was tested.

## Confirmed by you (2026-10-21, carried into plan v2)

1. **Mechanism:** `?expand=a,b` query parameter, a whitelist of allowed names per endpoint. Example: `GET /api/v1/management/event-log/{id}?expand=changed_by`. No generic `depth=N`.
2. **Default = ID only.** Without `expand` a link is only an ID (`changed_by`, `created_by`, `main_region_id`, ...). Asked for, it is the **full object**.
3. **Nothing is always expanded any more** on single GETs (also not what is expanded today). Speed checked: a plain GET is cheaper than before (POI 5 -> 3 SELECTs), the same content as before costs the same; each asked-for link costs about one small query (a user link two).
4. **Nested expand:** dotted paths up to 3 levels (`main_region.country.created_by`), several comma-separated paths merged (a shared parent counts once), at most 10 distinct links per request; an unknown name, a deeper path or more links answer 400 with the allowed names.
5. **Scope:** single-object GETs only.

## Answered 2026-10-26: "all recommended" (delivered to the repo, not yet on your host)

7 = **B** (an expanded user shows `id` and `username` to everybody; administrators and the user himself see the whole profile), 8 = all 33 endpoints, 9 = `null`, 10 = the plan has the host commands for both cases. Next step is yours: the commands of plan section 6 on the host (expect 506 files, hash `5a0dee4fcbd0cf7e`, pytest 107, `expand_check.py` 75 checks).

## The questions as they were asked (plan v2, section 2)

| # | Question | Recommendation |
|---|---|---|
| 7 | Who sees which fields of an expanded user? A = whole profile for everybody (as you decided); B = everybody sees id and username, administrators and the user himself see the whole profile; C = only id and username except administrators | **B**. The profile endpoints are administrator-only today and registration is open; with A, `?expand=created_by` on 27 of the 33 endpoints would hand out every creator's email, birth date, heart rates and group to anyone (tracks, gear and the compendium creators, editors included, are ordinary users). B is built and tested |
| 8 | Which endpoints get `expand`? | all 33 of the plan (section 3.1), including the new tracks, administrator job, settings, access policy |
| 9 | A link that was not asked for: key with `null`, or no key | `null` |
| 10 | Gate: does your host already run the Phase 3 layout? | tell me; the plan has the commands for both cases |

Assumption 6 of the plan (clean break): nothing besides your own scripts and Postman calls the single GETs; this is the answer you gave for the URL change.

## Defaults chosen in the plan (change by telling me)

- The answer field keeps the existing name (`compendium_type`, `main_region`); for users it is `created_by_user`, `changed_by_user`, `updated_by_user`, and `user` on the administrator's job, asked for as `created_by`, `changed_by`, `updated_by`, `user`.
- A plain gear answer stays as it is (no `created_by` added); the event-log compare endpoint takes `changed_by` and `entity_type` for both entries.
- An expanded object is shown by the rule "who may read the object you asked for", not by the policy of the linked object (no difference under today's policies).
- A request may have at most 10 links, 3 levels and 1000 characters.
- Not included: `/profile/users/{id}` and `/me`, your own job, Celery tasks, photos, `poi_access`, `gpx`, `geo_record`, the object a log entry is about.
- Lists keep their nested objects (a list item and a single GET differ on purpose).
