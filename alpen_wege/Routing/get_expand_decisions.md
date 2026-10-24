# GET `?expand=` - decisions

Scope: only single-object GET endpoints (`GET /something/{id}`). Lists, POST, PATCH and DELETE are not changed. No database change.

Implementation plan (for VS Code Claude): `get_expand_implementation_plan.md` (same folder). This file is the short list of decisions; the plan has the details.

## Confirmed by the user (2026-10-21)

1. **Mechanism:** `?expand=a,b` query parameter, a whitelist of allowed names per endpoint. Example: `GET /event-log/{id}?expand=changed_by`. No generic `depth=N`.
2. **Default = ID only.** Without `expand`, a link is returned only as its ID (`changed_by`, `created_by`, `main_region_id`, ...).
3. **Expanded = full representation** of the linked object. For a user that is the `UserRead` shape (email, birth date, heart rates, group; never the password hash).
4. **No field is always expanded any more on single GETs.** Fields that are expanded today (`entity_type`, `compendium_type`, `main_region`, `poi`, `rarity`, `country`, `parent`, `region_type`, `post_type`, `region`) also become opt-in. Speed check (asked for by the user): this does not slow anything down. The default request gets cheaper (fewer queries); each requested link costs one small extra query.
5. **Visibility rule: if you may read an object, you may see everything expanded inside it.** No extra permission check per expanded object. This includes the full user profile behind `created_by` / `changed_by`.
6. **Nested expand:** dotted paths up to 3 levels (for example `poi.main_region.country`), several comma-separated paths allowed and merged (shared parents are loaded once). Chosen option 2 (links declared once, any route can use them), accepted with "ok super" after the recommendation.
7. **Limits:** a request may expand at most 10 distinct links in total; a path deeper than 3 levels or an unknown name returns 400 with the allowed names.

## Defaults chosen in the plan (the user has not objected; can be changed)

- The expanded object goes into a sibling field next to the ID: `created_by_user`, `changed_by_user`; existing names (`compendium_type`, `main_region`, ...) stay.
- Unrequested links are present with the value `null` (alternative: omit the key).
- Event log: `changed_by` and `entity_type` on `/event-log/{id}` and on the compare endpoint (applies to both entries). The object a log entry is about (`entity_id`) and IDs inside `snapshot` are not resolved.
- `created_by` works on every object (one relationship in `CreatorMixin`). `GearDetail` also returns `created_by`. Difficulty-sports also get `sport_type`.
- Lists keep today's behaviour (nested objects always included), so a list item and a single GET differ on purpose.
- Rollout in 7 steps (E0 to E6), pilot on the event log and on POI first.

## Consequence to remember

With the seeded access policies every registered user (even `guest`) can read all compendium and reference data, and public gear. So with rule 5, any registered user can see the full profile (email, birth date, heart rates) of whoever created an object, including ordinary users who create public gear, and later public tracks and trips. It is a one-line switch in the code (`ExpandedUser` in `app/core/utils/expand.py`) to return only id and username instead. Recommended to revisit before tracks and trips get expand support.

## Open

None for the user. The implementing agent reports after each step.
