#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
[[ $# -eq 0 || ( $# -eq 1 && "$1" == --rebuild ) ]] || fail "Usage: bash 04_run.sh [--rebuild]"
load_session
[[ -f "$SESSION/preflight-ok" ]] || fail "Run first: 03_preflight.sh."
if [[ $# -eq 1 ]]; then
    echo "REBUILD: rebuilding historical data using only the inputs currently available."
    set -- --rebuild-db
else
    set --
fi
rm -f "$SESSION/run-ok"
# Repeat preflight in case configuration changed since step 03.
run_logged preflight-before-run "$PYTHON" -m qc_monitor.main --config "$CONFIG" --preflight --verbose
run_logged run "$PYTHON" -m qc_monitor.main --config "$CONFIG" --verbose "$@"
touch "$SESSION/run-ok"
echo "Run completed: execute 05_verify.sh to check acquisition and output."
