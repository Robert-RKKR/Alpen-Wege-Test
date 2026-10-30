#!/bin/bash
# Proves that a database migrated with scripts/sql/icons_ddl.sql equals a database that create_all builds from the new code.
#   OLD_REPO  = the repo as it was BEFORE the icons (extract backup_before_icons_2026-10-30.tar.gz: tar xzf ... app scripts)
#   NEW_REPO  = the repo with the icons
#   PG_BIN    = bin folder of a PostgreSQL with PostGIS and moddatetime; PG_PORT its port (superuser postgres, trust login)
#   PYTHON    = a python with the packages of requirements.txt
#   OLD_REPO=/tmp/old_repo NEW_REPO=/path/alpen_wege PG_BIN=/tmp/mm/pg/bin PG_PORT=5433 PYTHON=/tmp/venv/bin/python bash schema_diff.sh
# Last result (2026-10-30): 1342 statements in the migrated database, 1342 in the fresh one, 0 differences
# (the order of the columns inside a table is ignored: ALTER TABLE adds a column at the end).
set -e
export PATH=$PG_BIN:$PATH
P="psql -h localhost -p $PG_PORT -U postgres -q"
$P -c "DROP DATABASE IF EXISTS icons_old" -c "DROP DATABASE IF EXISTS icons_new" -c "CREATE DATABASE icons_old" -c "CREATE DATABASE icons_new" 2>/dev/null
mk() {   # repo database
  DATABASE_URL="postgresql+asyncpg://postgres@localhost:$PG_PORT/$2" DATABASE_URL_SYNC="postgresql+psycopg2://postgres@localhost:$PG_PORT/$2" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$1 \
  $PYTHON -c "
import asyncio
from app.database import create_tables, async_engine
async def main():
    await create_tables(); await async_engine.dispose()
asyncio.run(main())"
}
mk $OLD_REPO icons_old; mk $NEW_REPO icons_new
$P -d icons_old -v ON_ERROR_STOP=1 -f $NEW_REPO/scripts/sql/icons_preflight.sql > /dev/null
$P -d icons_old -v ON_ERROR_STOP=1 -f $NEW_REPO/scripts/sql/icons_ddl.sql
$P -d icons_old -v ON_ERROR_STOP=1 -f $NEW_REPO/scripts/sql/icons_ddl.sql          # a second run must change nothing
dump() { pg_dump -h localhost -p $PG_PORT -U postgres -s --no-owner --no-privileges "$1" | grep -v -E '^--|^SET |^SELECT pg_catalog|^$|^\\(un)?restrict'; }
dump icons_old > /tmp/icons_old_migrated.sql; dump icons_new > /tmp/icons_new_fresh.sql
python3 - <<'PY'
import re
def blocks(path):
    return [p.strip().rstrip(';') for p in re.split(r';\n(?=[A-Z])', open(path).read()) if p.strip()]
def norm(st):
    if st.startswith('CREATE TABLE'):
        head, _, rest = st.partition('(\n'); body, _, tail = rest.rpartition('\n)')
        return head + '(' + ';'.join(sorted(l.strip().rstrip(',') for l in body.split('\n'))) + ')' + tail
    return st
A = {norm(x) for x in blocks('/tmp/icons_old_migrated.sql')}; B = {norm(x) for x in blocks('/tmp/icons_new_fresh.sql')}
print(f"statements: migrated {len(A)}, fresh {len(B)}, only in migrated {len(A - B)}, only in fresh {len(B - A)}")
for x in sorted(A - B): print("  migrated> ", x[:300])
for x in sorted(B - A): print("  fresh>    ", x[:300])
raise SystemExit(1 if A != B else 0)
PY
