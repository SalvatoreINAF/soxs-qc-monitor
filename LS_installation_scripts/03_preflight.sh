#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
[[ $# -eq 0 ]] || fail "Usage: bash 03_preflight.sh"
load_session
[[ -f "$SESSION/install-ok" ]] || fail "Run first: 02_install.sh."
rm -f "$SESSION/preflight-ok"
run_logged preflight "$PYTHON" -m qc_monitor.main --config "$CONFIG" --preflight --verbose
run_logged inputs "$PYTHON" "$SCRIPT_DIR/diagnostics.py" inputs
touch "$SESSION/preflight-ok"
echo "Preflight completed. Also review warnings in the inputs log."
