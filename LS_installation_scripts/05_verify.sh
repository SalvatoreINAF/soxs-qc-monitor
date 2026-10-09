#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
[[ $# -eq 0 ]] || fail "Usage: bash 05_verify.sh"
load_session
[[ -f "$SESSION/run-ok" ]] || fail "The last run did not complete successfully: check run.log."
run_logged verification "$PYTHON" "$SCRIPT_DIR/diagnostics.py" verify
echo "Automated checks passed. Open the report and review its dates and plots."
echo "Keep this directory: $SESSION"
