# List filter `name`: all languages, ignoring case and accents (proposal)

Proposal, 2026-10-28. **Nothing is changed in the repo.** It narrows `get_filters_language_columns_proposal.md` to what you asked for: a filter for the **name** only (no `summary` or `description` filters), so that `GET /api/v1/compendium/pois?name=zurich` finds **Zürich**.

## 1. What you get

A new filter `name` on every list whose model has a name in several languages. It searches `name`, `name_de` and `name_pl` (and `name_fr` the day it exists) in one go, ignores upper and lower case, ignores accents and treats `ä ö ü ß ł ó ń ...` as `a o u ss l o n`, and a part of a word is enough.

| Request | Finds |
|---|---|
| `GET /api/v1/compendium/pois?name=zurich` | Zürich, ZÜRICH, Zurich (the three spellings match the same rows) |
| `GET /api/v1/compendium/pois?name=zermat` | Zermatt |
| `GET /api/v1/compendium/pois?name=strasse` | anything with Straße or Strasse in any language name |
| `GET /api/v1/compendium/regions?name=lodz` | Łódź (found through the Polish name) |
| `GET /api/v1/core/rarities?name=selten` | lookup tables work the same way |
| `GET /api/v1/compendium/pois?name=zurich&altitude_min=400&sort=-altitude_m&limit=50` | combines with every other filter (AND) |

Lists that get `name`: POIs, regions, countries, cards, posts, gear, tracks, routes, segments, GPX files, photos, the 19 lookup tables and resource types. Users have no multilanguage name and keep their own `q`. Everything else about a list (paging, sort, other filters) is unchanged.

Measured on your data (20,758 POIs): today `name=zurich` with a plain search finds **0** POIs, because 3,811 POI names contain an umlaut or ß; with accents ignored it finds **488**.

## 2. How it works

- **Database:** PostgreSQL's own `unaccent` extension (it ships with PostgreSQL; your `postgis/postgis:15` image has it). One small script, run once like the other database scripts:

  ```sql
  -- scripts/sql/search_unaccent.sql (idempotent)
  CREATE EXTENSION IF NOT EXISTS unaccent;
  CREATE OR REPLACE FUNCTION public.f_unaccent(text) RETURNS text
      LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
      AS $$ SELECT public.unaccent('public.unaccent', $1) $$;
  ```

  The wrapper `f_unaccent` is what lets an index be built on the accent-free text later (`unaccent` itself is not allowed in an index). `CREATE EXTENSION unaccent` is allowed for the database owner (the extension is marked trusted since PostgreSQL 13). Tested on the sandbox database.
- **Query:** `f_unaccent(name) ILIKE f_unaccent('%zurich%') OR f_unaccent(name_de) ILIKE ... OR f_unaccent(name_pl) ILIKE ...`. `%`, `_` and `\` typed by the user stay ordinary characters (escaped before the pattern is built, as in the existing filters).
- **Columns are found from the model**, not written in the list: a helper `localized(M)["name"]` returns `name`, `name_de`, `name_pl` and any `name_<xx>` text column. A new language needs no list edited. A test fails if a model has a name family and its list has no `name` parameter.
- **Safe on deployment:** the app checks once (cached) whether `f_unaccent` exists. If the script has not been run yet, `name` still works but only ignores case (plain `ILIKE`), so a forgotten script never causes a `500`; the log says so once. After the script has been run, restart the API once (the check is cached) and accents are ignored.
- **Code:** one new function in `app/core/utils/listing.py` (`name_contains`), one explicit `name` parameter and one line in `apply()` of each of the 12 `get_many.py` files that write name columns by hand (11 lists with `q` and resource types), and in the shared `NameFilters` (19 lookup tables). Same explicit style as the other filters, so Swagger shows `name` with its description.

## 3. Speed

Measured (database time of one search with no match, i.e. every row is read; a list call runs the search twice, for the total and for the page):

| | Plain | Accents ignored | Accents ignored, with an index |
|---|---|---|---|
| Names, your 20,758 POIs | 10 ms | 41 ms | about 1 ms for a word of three or more letters |
| Names, 5,000 synthetic rows | 6 ms | 27 ms | not needed |

So a name search on the biggest list (POIs) costs about 80 ms per call instead of 20 ms; every other list has far fewer rows (regions 1,570, countries 250, lookup tables under 250) and stays in a few milliseconds. The slowdown comes from removing the accents of every row before comparing. **No index is needed today.** If a table grows to hundreds of thousands of rows, the ready statement is `CREATE INDEX CONCURRENTLY ... USING gin (public.f_unaccent(name) gin_trgm_ops)` per name column (`pg_trgm` is already installed); a two-character word cannot use it and still reads every row, which is fine at these sizes.

## 4. Decisions (my recommendation first)

| # | Question | Recommendation |
|---|---|---|
| 1 | Add the filter `name` (all languages, ignoring case and accents) to every list that has a multilanguage name? | **Yes** |
| 2 | Accents only (`ü` = `u`), or also the German spelling `ue/oe/ae` (so `zuerich` finds Zürich)? | **Accents only**, as you described. Matching `ue/oe/ae` as well is possible later, but `ue` also occurs in ordinary words ("Quelle"), so it needs its own look |
| 3 | The existing `q` (search box) keeps its plain case-insensitive search, or also ignores accents in the name part? | **Keep `q` as it is** for now: smallest change, you asked for the name filter only. If `q=zurich` should find Zürich too, it is the same call and I add it |
| 4 | If the SQL script has not been run, `name` falls back to case-insensitive only (no error)? | **Yes** |
| 5 | Minimum of 2 characters for `name` as for `q`? | **Yes** |
| 6 | Trigram indexes on the accent-free names? | **Later**, when a table is large; the statements stay in the plan |

## 5. How it would be built and checked

Same procedure as the list filters: a scratch copy of the current repo, one script that applies the change and refuses to run on files that are not in the expected state, checks in the scratch copy (unit tests, route map compare, live check on a real PostgreSQL with and without the extension, the three library stacks), one delivery, then your host commands.

- **Tests:** `name_contains` builds the expected SQL (accent wrapper, all name columns, escaped pattern); every list with a name family has a `name` parameter and uses all its name columns (generic test, so a missing language column is found); the fallback when the function is missing; `localized()` finds `name`, `name_de`, `name_pl` and a throwaway model's `name_fr` but not `name_id`.
- **Live check** (PostgreSQL with `unaccent`): a POI named "Zürich" is found by `name=zurich`, `name=ZURICH`, `name=zürich`; a row with only `name_pl` = "Łódź" is found by `name=lodz`; `name=zuerich` does not find Zürich (decision 2); `name=%` is an ordinary character; the same requests without the extension still work and find by case only.
- **Postman:** `name` appears (switched off) in the list requests when the collection is rebuilt; Swagger gets its description.
- **Host:** one new SQL script (`scripts/sql/search_unaccent.sql`) in the deployment runbook, run before the application starts. Rollback is the usual file copy; the extension and the function can stay (harmless) or be dropped with `DROP FUNCTION public.f_unaccent(text); DROP EXTENSION unaccent;`.
- **Risks:** a slower name search on POIs (section 3, measured); the extension missing on a host database (covered by the fallback and the script); users who expect `ue` to match `ü` (decision 2).

Answer with the numbers you accept (for example "1 yes, 2 accents only, 3 keep q, 4 yes, 5 yes, 6 later") or "accept all recommended".
