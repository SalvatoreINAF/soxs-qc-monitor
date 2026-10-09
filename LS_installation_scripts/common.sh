#!/usr/bin/env bash
# Shared helpers; invoke the numbered scripts with bash.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO/configs/qc_monitor.yaml"
STATE="$SCRIPT_DIR/local"
export REPO CONFIG
export QC_MONITOR_ROOT="$REPO"
export MPLBACKEND=Agg
fail() { echo "ERROR: $*" >&2; exit 1; }
[[ -f "$CONFIG" ]] || fail "Configuration file missing: $CONFIG"
cd "$REPO"
load_session() {
    [[ -f "$STATE/session" ]] || fail "Run first: 01_backup.sh."
    SESSION="$(cat "$STATE/session")"
    [[ -d "$SESSION" && -f "$SESSION/backup-ok" ]] || fail "Backup incomplete."
    export SESSION
    PYTHON="$(cat "$SESSION/python-path")"
    [[ -x "$PYTHON" ]] || fail "Python interpreter unavailable: $PYTHON"
    export MPLCONFIGDIR="$STATE/matplotlib"
    mkdir -p "$MPLCONFIGDIR"
}
run_logged() {
    local name="$1"
    shift
    echo "Log: $SESSION/$name.log"
    if "$@" > "$SESSION/$name.log" 2>&1; then
        tail -n 30 "$SESSION/$name.log"
    else
        local code=$?
        tail -n 80 "$SESSION/$name.log"
        echo "Operation failed (exit code $code). Do not continue." >&2
        return "$code"
    fi
}
