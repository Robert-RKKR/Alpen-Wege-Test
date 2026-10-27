#!/bin/bash
# usage: stack_run.sh s1|s2   (runs unit tests, route_map, live list check on that library stack)
S=$1; PY=/tmp/ex/$S/bin/python
source /tmp/ex/env.sh
echo "== $S: $($PY -c 'import fastapi,starlette,pydantic,sqlalchemy,sys;print(sys.version.split()[0],fastapi.__version__,starlette.__version__,pydantic.VERSION,sqlalchemy.__version__)')"
cd /tmp/ex/cur && PYTHONPATH=/tmp/ex/cur $PY scripts/route_map.py dump /tmp/ex/route_dumps/${S}_before.json | tail -1
cd /tmp/ex/new && PYTHONPATH=/tmp/ex/new $PY scripts/route_map.py dump /tmp/ex/route_dumps/${S}_after.json | tail -1
PYTHONPATH=/tmp/ex/new $PY scripts/route_map.py compare /tmp/ex/route_dumps/${S}_before.json /tmp/ex/route_dumps/${S}_after.json --lists 2>&1 | tail -3
PYTHONPATH=/tmp/ex/new $PY scripts/route_map.py probe /tmp/ex/route_dumps/${S}_after.json | tail -1
PYTHONPATH=/tmp/ex/new $PY scripts/route_map.py names | tail -1
$PY -m pytest tests -q 2>&1 | tail -3
cd /tmp/ex && bash down.sh; PYBIN=$PY AW_DIR=new bash up2.sh
cd /tmp/ex/new && $PY scripts/list_check.py --gpx /tmp/ex/full.gpx > /tmp/ex/list_check_$S.txt 2>&1
grep -c "^PASS" /tmp/ex/list_check_$S.txt; grep -v "^PASS" /tmp/ex/list_check_$S.txt | head -12
bash /tmp/ex/down.sh
