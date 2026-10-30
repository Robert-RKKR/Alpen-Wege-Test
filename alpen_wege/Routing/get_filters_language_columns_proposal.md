# List filters: search every multilanguage field the same way (proposal v2)

Proposal v2, 2026-10-28 (v1 only covered `name`; you asked for all multilanguage fields: `name`, `summary`, `description`). **Nothing is changed in the repo.** The idea: no list names a language column. A helper reads the model, finds every multilanguage field (`name`, `name_de`, `name_pl`, `summary`, `summary_de`, ..., and any field or language added later). You can filter by the field itself: `?name=zermat` searches all name columns, `?description=bahn` all description columns. v2 (after your question "why not `?name=zermat`?") replaces the `q_in` parameter of the first v2 draft with exactly that: one filter per field, named after the field.

## 1. How it works today

The text filter `q` of each list has its columns written out by hand in `app/*/routes/*/get_many.py`:

| List | `q` searches today | What is missing |
|---|---|---|
| POIs, regions, countries, cards, posts, routes, segments, GPX files | `name`, `name_de`, `name_pl` | all `summary*` and `description*` columns |
| Photos | `name*` and `summary*` (three languages each) | `description` has none |
| Tracks | `name*` and **only** `summary` | `summary_de`, `summary_pl`, `description*` |
| Gear | `name*` and `model` | `summary*`, `description*` |
| The 19 lookup tables (shared `NameFilters`) | `name*` | nothing (they have no other language field) |
| Resource types | **only** `key` | `name*` |
| Users | `username`, `email`, `first_name`, `last_name` | not a language field, unchanged |

The lists are consistent only by luck: tracks forgot two summary languages, resource types search no name, and no list searches a description. A fourth language (`name_fr`, `summary_fr`, ...) means editing 12 `get_many.py` files plus the shared `NameFilters`, and a forgotten file silently does not search it.

The multilanguage fields in the code: every table with `NameL18nMixin`, `SummaryL18nMixin`, `DescriptionL18nMixin` (assets, compendium catalog, gear, routes, segments, tracks, trips, journeys, achievements): `name`, `summary`, `description`, each with `_de` and `_pl`.

## 2. The proposal

**One helper finds the fields from the model**, in `app/core/utils/listing.py`:

```python
localized(M)           # {"name": (M.name, M.name_de, M.name_pl),
                       #  "summary": (M.summary, M.summary_de, M.summary_pl),
                       #  "description": (M.description, M.description_de, M.description_pl)}
localized(CoreRefRarity)   # {"name": (...)} only: it has no other multilanguage field
```

A multilanguage field is a text column `X` that has siblings `X_<two letters>`; the helper takes the whole family. Nothing in the code says `name`, `summary` or `description`, so a new field (`title`, `title_de`) or a new language (`name_fr`) is found the day it exists. Columns that only look similar are never taken (`name_id` is a link, not text; `first_name` has no `first` column). The result is cached per model.

**One filter per field, named after the field.** Each list that has a multilanguage field gets a filter parameter with that field's name; it searches every language column of the field (not case sensitive, part of a word is enough, at least 2 characters, `%` and `_` are ordinary characters):

```python
class PoiFilters:
    def __init__(self, ...,
                 name: str | None = search_query("name in every language"),
                 summary: str | None = search_query("summary in every language"),
                 description: str | None = search_query("description in every language"),
                 q: str | None = search_query("any multilanguage field")): ...
    def apply(self, stmt):
        fields = localized(M)
        return where_all(stmt, contains(self.name, *fields["name"]), contains(self.summary, *fields["summary"]),
                         contains(self.description, *fields["description"]), contains(self.q, *chain.from_iterable(fields.values())), ...)
```

The parameters are written out in each list (so Swagger shows them, as it shows every other filter); **the columns behind them are never written**: `fields["name"]` is `name`, `name_de`, `name_pl` today and `name_fr` the day it exists. A test fails when a model has a multilanguage field that its list has no parameter for, so a new field cannot be forgotten silently.

**`q` stays** as the "search everywhere" box: the word in any multilanguage field of the list's model (all fields, all languages). `name`, `summary` and `description` narrow to one field. Different filters are combined with AND (`?name=zermat&description=bahn` means a name with zermat and a description with bahn). Lists keep their own extra text columns inside `q` (gear `model`, users).

What this changes for callers: `?name=...` is new; `q` finds more rows than today (it now includes the summaries and descriptions). Example, your 20,758 POIs, searching `bahn`: 869 POIs by name, 2,382 by name or summary. Anything found today is still found. Tracks, gear and resource types also gain what the table of section 1 lists as missing.

## 2b. What a request looks like

| Request | What is searched |
|---|---|
| `GET /api/v1/compendium/pois?name=zermat` | `zermat` in `name`, `name_de` and `name_pl` of a POI (finds Zermatt) |
| `GET /api/v1/compendium/pois?description=bahn` | only the descriptions (`description`, `description_de`, `description_pl`) |
| `GET /api/v1/compendium/pois?name=zermat&summary=bahn` | a name with `zermat` **and** a summary with `bahn` |
| `GET /api/v1/compendium/pois?q=bahn` | `bahn` anywhere: all names, summaries and descriptions in all languages |
| `GET /api/v1/core/rarities?name=selten` | a lookup table has only `name`, so only `name` (and `q`) exist |
| `GET /api/v1/compendium/pois?name=zermat&altitude_min=1000&sort=-altitude_m&limit=50` | combines with every other filter |

A filter for a field the list's model does not have is simply not a parameter of that list (`?summary=x` on a lookup table is ignored like any unknown parameter; Swagger shows what each list has).

## 3. Cost: measured, and the one real caveat

Searching text with `ILIKE '%word%'` reads every row that is not excluded by an index. The seed of this sandbox has short summaries and empty descriptions, so today's cost is small. With **realistic long texts** (summary about 1 KB and description about 2 KB per row, three languages each, 5,000 rows measured, 20,000 rows is four times that):

| Search over | No index | With a trigram index on every column |
|---|---|---|
| the three names (today) | 10 to 35 ms per 20,000 rows | not needed |
| names and summaries (6 columns) | about 400 ms per 20,000 rows | sub-millisecond |
| names, summaries and descriptions (9 columns) | **about 880 ms per 20,000 rows** (218 ms per 5,000) | **0.4 ms** for a word of three or more characters |

Two things to know: a list call runs the search twice (the total and the page), so double the no-index numbers; and a trigram index cannot help a search word of **two** characters (the filter allows two), which still reads every row (about 230 ms per 5,000 rows). The index needs space: in my worst case (random text) about 2.5 times the text, with real prose less. Index creation is a one-time `CREATE INDEX CONCURRENTLY` per column (2 to 4 seconds per column per 5,000 long rows). `pg_trgm` is already installed in your database. The DDL for all multilanguage columns of the seven catalog tables is ready to put in the plan (the earlier list-filters plan, section 6.5, has the pattern).

At your current data (short summaries, no descriptions) no index is needed. The advice is to add the trigram indexes when descriptions are filled, or at once if you prefer to be ahead of the data.

## 4. Decisions (my recommendation first)

| # | Question | Recommendation |
|---|---|---|
| 1 | Find all multilanguage fields and their language columns from the model (no list names `name_pl`, `summary_de`, ...)? | **Yes.** A new language needs no list edited |
| 2 | Filter parameters named after the field (`name`, `summary`, `description`), each searching all languages of that field? | **Yes.** It is the clearest form (`?name=zermat`) and replaces the `q_in` idea of the first draft |
| 3 | What does `q` do after that: **(a)** searches every multilanguage field (name, summary, description), **(b)** only the names as today, or **(c)** names and summaries | **(a)**, "search everywhere"; the per-field parameters are the way to narrow. It costs nothing at today's data; with long descriptions add trigram indexes (section 3). If you want every `q` to stay fast without an index, (c) is the safe middle |
| 4 | Keep the minimum of 2 characters for all these text filters? | **Keep.** Two-character searches stay a full read (fine at 20,000 rows); 3 would let every search use an index |
| 5 | Lists with their own text columns (gear `model`, users) keep them inside `q`? | **Yes** |
| 6 | Build the trigram indexes now (SQL scripts you run) or later? | **Later**, when descriptions are filled; the plan will have the statements and the check |

## 5. How it would be built and checked

Same procedure as the list filters: a scratch copy of the current repo (it changed since 26.10.: assets, routes, segments), one script that applies the change and refuses to run on files that are not in the expected state, then the checks, then one delivery. No database change; the indexes of decision 6 are separate.

- Changed: `app/core/utils/listing.py` (`localized`, the shared `NameFilters` gets the `name` filter), the 12 `get_many.py` files that write columns by hand (11 lists with `q` and resource types), README paragraph on text search, Swagger text of `q` and of the new filters.
- Tests: `localized()` finds the three fields and their languages on a real model, finds a throwaway model's `name_fr` and `title_de`, and never takes `name_id` or `first_name`; every list searches exactly the multilanguage fields of its model (the existing column test becomes generic instead of a hand-written table); a model with a multilanguage field that its list has no parameter for fails the test; tracks search `summary_pl` and `description_de` with `summary=` and `description=`; resource types search `name_pl`; a list's own extra columns (`model`, users) stay.
- Live check: a row with only `description_pl` or `name_pl` filled is found by `q` on a POI, a track and a lookup table; `?name=` does not find it by its description, `?q=` does.
- Postman: `name`, `summary`, `description` appear (switched off) in the list requests when the collection is rebuilt.
- Risks: a result set that grows (intended, listed in section 2); slower search on a big table with long texts (section 3, the index is the answer); a column that only looks like a language field (guarded by type check and tests). Rollback is the usual file copy; a backup is made first.

Answer with the numbers you accept (for example "1 yes, 2 yes, 3 (a), 4 keep, 5 yes, 6 later") or "accept all recommended".
