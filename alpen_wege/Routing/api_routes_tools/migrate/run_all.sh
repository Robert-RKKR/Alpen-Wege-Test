#!/bin/bash
# Runs the routes migration step by step and checks the result after every step.
# Reference runner for Routing/api_routes_implementation_plan.md (tested in a sandbox on 2026-10-24).
#
#   AW_ROOT=<scratch copy to change> AW_OLD=<untouched copy of the same repo> \
#   AW_PY=<python that can import app, with pytest> AW_PYLIB=<folder with autoflake> ./run_all.sh [phase1|phase2|all]
#
# Run it on a COPY in /tmp first (about two minutes), look at the result, then deliver the changed files to the real
# repo with deliver.py. The scripts stop with an error when a file does not look as they expect.
#
# Needs in AW_ROOT before the first run: scripts/route_map.py, scripts/ast_compare.py, scripts/route_rules.json
# (plan step 0.3) and route_dumps/before.json (plan step 0.4, made from the untouched code); for phase3
# route_dumps/before3.json (dump of the repo as it is before phase 3, AW_OLD = a copy of that state).
# AW_SKIP_PYTEST=1 skips the pytest gate (only for a Python without pytest).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${AW_ROOT:?set AW_ROOT to the scratch copy to change}" && pwd)"
OLD="$(cd "${AW_OLD:?set AW_OLD to an untouched copy of the repo}" && pwd)"
PY="${AW_PY:-python3}"
WHAT="${1:-all}"
cd "$ROOT"
RM="$PY -B -I scripts/route_map.py"

# The six tests that fail in the untouched repo (they belong to the GPX code, not to this work)
KNOWN_FAILURES="tests/test_gpx_pipeline.py::test_straight_line_distance
tests/test_matching.py::test_nearest_visit_edge_projection
tests/test_matching.py::test_nearest_visit_no_timestamps
tests/test_matching.py::test_nearest_visit_on_track
tests/test_matching.py::test_nearest_visit_outside_radius
tests/test_matching.py::test_nearest_visit_time_interpolation"

pytest_gate() {   # $1 = the tests that may fail (default: the six known failures of 2026-10-24; phase 3 passes "none")
  if ! $PY -c "import pytest" 2>/dev/null; then
    if [ "${AW_SKIP_PYTEST:-0}" = "1" ]; then echo "-- pytest skipped (AW_SKIP_PYTEST=1)"; return 0; fi
    echo "STOP: pytest is not installed for AW_PY (install it, or set AW_SKIP_PYTEST=1)"; return 1
  fi
  local out failed
  out="$($PY -B -m pytest -q --no-header -p no:cacheprovider -rf 2>&1 || true)"
  failed="$(echo "$out" | grep '^FAILED' | sed 's/^FAILED //; s/ - .*//' | sort | sed '/^$/d' || true)"
  echo "-- pytest: $(echo "$out" | tail -1)"
  local allowed="${1-$KNOWN_FAILURES}"
  [ "$allowed" = "none" ] && allowed=""
  if [ "$failed" != "$(echo "$allowed" | sort | sed '/^$/d')" ]; then
    echo "STOP: the failing tests are not exactly the allowed ones. Failing now:"; echo "$failed"; return 1
  fi
}

phase1() {
  [ -f route_dumps/before.json ] || { echo "route_dumps/before.json is missing (plan step 0.4)"; exit 1; }
  local n=0
  for s in m1_1_ref m1_2_profile m1_3_management m1_4_folders m1_5_scope; do
    n=$((n + 1))
    echo "== step 1.$n ($s)"
    AW_ROOT="$ROOT" "$PY" -B "$HERE/$s.py"
    $RM dump "route_dumps/after_1_$n.json" > /dev/null
    $RM compare route_dumps/before.json "route_dumps/after_1_$n.json"        # must say: identical
  done
  echo "== end of phase 1: probe, undefined names, code comparison, tests"
  $RM probe route_dumps/after_1_5.json
  $RM names
  $PY -B scripts/ast_compare.py "$OLD" "$ROOT" --phase 1
  pytest_gate
}

phase2() {
  [ -f route_dumps/before.json ] || { echo "route_dumps/before.json is missing (plan step 0.4)"; exit 1; }
  for st in 0 1 2 3 4 5 6; do
    echo "== step 2.$st"
    AW_ROOT="$ROOT" "$PY" -B "$HERE/m2_urls.py" "$st"
    $RM dump "route_dumps/after_2_$st.json" > /dev/null
    $RM compare route_dumps/before.json "route_dumps/after_2_$st.json" --rules scripts/route_rules.json --step "$(( st > 4 ? 4 : st ))"
  done
  echo "== end of phase 2: all rules, probe, undefined names, code comparison, tests"
  $RM compare route_dumps/before.json route_dumps/after_2_6.json --rules scripts/route_rules.json
  $RM probe route_dumps/after_2_6.json
  $RM names
  $PY -B scripts/ast_compare.py "$OLD" "$ROOT"
  pytest_gate
}

phase3() {
  # uniform layout: before3.json is the dump of the repo state before phase 3 (same URLs), AW_OLD = that state
  [ -f route_dumps/before3.json ] || { echo "route_dumps/before3.json is missing (dump of the repo before phase 3)"; exit 1; }
  for st in 1 2 3 4; do
    echo "== step 3.$st"
    AW_ROOT="$ROOT" "$PY" -B "$HERE/m3_uniform.py" "$st"
    $RM dump "route_dumps/after3_$st.json" > /dev/null
    $RM compare route_dumps/before3.json "route_dumps/after3_$st.json"          # must say: identical
  done
  echo "== step 3.5 (standard test)"
  AW_ROOT="$ROOT" "$PY" -B "$HERE/m3_uniform.py" 5
  echo "== end of phase 3: probe, undefined names, code comparison, tests"
  $RM probe route_dumps/after3_4.json
  $RM names
  $PY -B scripts/ast_compare.py "$OLD" "$ROOT" --phase 3
  pytest_gate none
}

case "$WHAT" in
  phase1) phase1 ;;
  phase2) phase2 ;;
  phase3) phase3 ;;
  all) phase1; phase2 ;;
  *) echo "usage: run_all.sh [phase1|phase2|phase3|all]"; exit 2 ;;
esac
echo "DONE: $WHAT"
