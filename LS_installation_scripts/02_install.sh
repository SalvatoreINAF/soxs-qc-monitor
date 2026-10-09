#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
[[ $# -eq 0 ]] || fail "Usage: bash 02_install.sh"
load_session
rm -f "$SESSION/install-ok" "$SESSION/preflight-ok" "$SESSION/run-ok"
run_logged install "$PYTHON" -m pip install .
run_logged dependencies "$PYTHON" -m pip check
touch "$SESSION/install-ok"
echo "Installation completed."
