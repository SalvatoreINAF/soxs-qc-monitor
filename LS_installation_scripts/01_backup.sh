#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
[[ $# -eq 0 ]] || fail "Usage: bash 01_backup.sh"
command -v python >/dev/null || fail "Activate the production Python environment first."
[[ "$(git branch --show-current)" == main ]] || fail "The clone must be on the main branch."
mkdir -p "$STATE"
SESSION="$(mktemp -d "$STATE/session-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
export SESSION
python -c 'import sys; print(sys.executable)' > "$SESSION/python-path"
cp -p "$CONFIG" "$SESSION/qc_monitor.yaml"
git rev-parse HEAD > "$SESSION/commit.txt"
git status --short > "$SESSION/git-status.txt"
python -m pip freeze > "$SESSION/packages.txt"
python "$SCRIPT_DIR/diagnostics.py" backup
touch "$SESSION/backup-ok"
printf '%s\n' "$SESSION" > "$STATE/session"
echo "Backup completed: $SESSION"
echo "Python interpreter selected for all steps: $(cat "$SESSION/python-path")"
