# icons_import

The graphics for all icon texts of the reference tables (made 2026-10-30 from your `icon_names.csv`).

| File | What |
|---|---|
| `icon_set.xlsx` | sheet `README` (how to use it, counts), sheet `icons` (the list to edit: names, kind, value, color, tag; yellow = editable), sheet `import` (the finished list with the SVG text of every icon) |
| `icons_import.csv` | the sheet `import` as CSV UTF-8: load it with `seed_icons.py --csv` |
| `icon_preview.html` | open in a browser: every icon with its key and name |

438 icons: 356 Lucide glyphs (113 with exactly the Lucide name of your key), 67 difficulty-grade badges, 15 level-bar icons. 47 rows are marked `redraw` in the sheet `icons` (the same glyph is used several times in one table, for example five snowflakes among the sports; the six bike sports are told apart by a two-letter tag). Names in German and Polish come from your seed data (67 icons have none: companies, gear types and the like that stand for many rows).

**Import with one API call:** `POST /api/v1/assets/icons/upload-csv` with `icons_import.csv` as `file` (first `?dry_run=true`); in Postman: `assets / icons / Upload icons CSV (dry run)` and `(import all)`. With the default `link=true` the reference rows get their `icon_id` in the same call. Or with the script: see the `README` sheet or `../icons_deploy_runbook.md` section 5b. The generator and the map live in the repo (`scripts/make_icon_set.py`, `scripts/icon_sources/`).
