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
# (plan step 0.3) and route_dumps/before.json (plan step 0.4, made from the untouched code).
# AW_SKIP_PYTEST=1 skips the pytest gate (only for a Python without pytest).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${AW_ROOT:?set AW_ROOT to the scratch copy to change}" && pwd)"
OLD="$(cd "${AW_OLD:?set AW_OLD to an untouched copy of the repo}" && pwd)"
PY="${AW_PY:-python3}"
WHAT="${1:-all}"
cd "$ROOT"
[ -f route_dumps/before.json ] || { echo "route_dumps/before.json is missing (plan step 0.4)"; exit 1; }
RM="$PY -B -I scripts/route_map.py"

# The six tests that fail in the untouched repo (they belong to the GPX code, not to this work)
KNOWN_FAILURES="tests/test_gpx_pipeline.py::test_straight_line_distance
tests/test_matching.py::test_nearest_visit_edge_projection
tests/test_matching.py::test_nearest_visit_no_timestamps
tests/test_matching.py::test_nearest_visit_on_track
tests/test_matching.py::test_nearest_visit_outside_radius
tests/test_matching.py::test_nearest_visit_time_interpolation"

pytest_gate() {   # stops the run when any test fails that is not one of the six known failures
  if ! $PY -c "import pytest" 2>/dev/null; then
    if [ "${AW_SKIP_PYTEST:-0}" = "1" ]; then echo "-- pytest skipped (AW_SKIP_PYTEST=1)"; return 0; fi
    echo "STOP: pytest is not installed for AW_PY (install it, or set AW_SKIP_PYTEST=1)"; return 1
  fi
  local out failed
  out="$($PY -B -m pytest -q --no-header -p no:cacheprovider -rf 2>&1 || true)"
  failed="$(echo "$out" | grep '^FAILED' | sed 's/^FAILED //; s/ - .*//' | sort || true)"
  echo "-- pytest: $(echo "$out" | tail -1)"
  if [ "$failed" != "$(echo "$KNOWN_FAILURES" | sort)" ]; then
    echo "STOP: the failing tests are not exactly the 6 known ones. Failing now:"; echo "$failed"; return 1
  fi
}

phase1() {
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

case "$WHAT" in
  phase1) phase1 ;;
  phase2) phase2 ;;
  all) phase1; phase2 ;;
  *) echo "usage: run_all.sh [phase1|phase2|all]"; exit 2 ;;
esac
echo "DONE: $WHAT"
