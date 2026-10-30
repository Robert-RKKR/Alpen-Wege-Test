# icons_tools

Tools of the icons work (2026-10-30). The delivered code is in the repo: `app/assets/` (model `AssetAggIcon`, `routes/icon/`, `services/icon_*.py`),
`scripts/sql/icons_*.sql`, `scripts/seed_icons.py`, `scripts/icons_check.py`, `tests/test_icons.py`, `tests/test_icon_svg.py`.
Plan and decisions: `../icons_implementation_proposal.md`; what was delivered and measured: `../icons_delivery.md`.

| File | What |
|---|---|
| `test_icons_migration.py` | 13 tests of the migration (preflight, DDL twice, old application code, table rules, trigger, loader, linking by key, RESTRICT, rollback, rollback then DDL) on a real PostgreSQL with the real seed data (643 reference rows incl. `Ship`/`ship`, 250 countries, 1,570 regions) and the 270 real flags. Needs `MIG_PG_URI`, `MIG_PG_BIN`, `ALPEN_DIR` (see its docstring) and a python with the packages of `requirements.txt` |
| `schema_diff.sh` | builds the OLD code's database, migrates it with `icons_ddl.sql`, builds the NEW code's database with `create_all` and compares both schemas statement by statement (result: 0 differences) |

The drafts that were here before (`icons_*.sql`, `seed_icons.py`, `icon_svg_prototype.py` and its tests) are now the repo files above.
