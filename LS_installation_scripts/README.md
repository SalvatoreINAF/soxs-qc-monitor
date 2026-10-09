# QC Monitor update — La Silla

Run these commands in Bash from the production clone root, after reductions have finished. Suspend scheduled monitor runs and make sure no other process is using the QC database. Do not run the scripts concurrently.

## Before downloading the scripts

The local code has not been modified, but the configuration may contain machine-specific paths. Save it before pulling. Replace the clone path in the following command:

```bash
bash
cd /path/to/clone/soxs-qc-monitor
BOOTSTRAP_BACKUP=$(mktemp -d "$HOME/qc-monitor-config-XXXXXXXX")
cp -p configs/qc_monitor.yaml "$BOOTSTRAP_BACKUP/qc_monitor.yaml"
git rev-parse HEAD > "$BOOTSTRAP_BACKUP/previous-commit.txt"
git branch --show-current
git status --short
```

The branch must be `main`. If there are local code changes, stop. Stash only the configuration, then update:

```bash
git stash push -m "La Silla configuration before update" -- configs/qc_monitor.yaml
git pull --ff-only origin main
```

**If the pull fails, stop. Do not use reset --hard.** After a successful pull:

```bash
cp -p configs/qc_monitor.yaml "$BOOTSTRAP_BACKUP/qc_monitor-main-new.yaml"
cp -p "$BOOTSTRAP_BACKUP/qc_monitor.yaml" configs/qc_monitor.yaml
diff -u "$BOOTSTRAP_BACKUP/qc_monitor-main-new.yaml" configs/qc_monitor.yaml
```

`diff` returns 1 when differences are found: this is normal. Keep the machine-specific paths and incorporate any new options required by the repository README. The stash is retained as an additional backup; do not run `stash pop`, since the configuration has already been restored.

## Run the scripts in order

Activate the environment actually used in production, usually:

```bash
conda activate soxspipe
python --version
command -v python
```

If Conda is unavailable in the new Bash shell, initialize it according to the local setup. A Python version compatible with `pyproject.toml` and PyYAML (already a monitor dependency) are required. Installation updates packages in this environment: if it is shared with the pipeline, keep the pipeline stopped during the operation.

```bash
bash LS_installation_scripts/01_backup.sh
bash LS_installation_scripts/02_install.sh
bash LS_installation_scripts/03_preflight.sh
```

Run one command at a time. **If an error occurs, do not continue.**

1. `01_backup.sh`: saves the configuration, current commit, package list, and a verified SQLite backup. The commit preceding the pull is recorded in the initial backup. Selects the Python interpreter for all subsequent steps.
2. `02_install.sh`: installs the code from the clone and checks dependencies.
3. `03_preflight.sh`: checks the configuration and counts discoverable dispersion FITS files. Also reports files in the adjacent `qc` directory. Does not move or modify inputs.

Normal execution, preserving historical data:

```bash
bash LS_installation_scripts/04_run.sh
```

**Alternatively**, rebuild the entire QC database:

```bash
bash LS_installation_scripts/04_run.sh --rebuild
```

Use `--rebuild` only if all inputs needed to reconstruct the desired historical data are still available. This option explicitly authorizes rebuilding; no additional confirmation is requested. The backup precedes installation. The upstream `soxspipe.db` database is not rebuilt.

Finally:

```bash
bash LS_installation_scripts/05_verify.sh
```

Verification checks SQLite integrity, row counts, report and PNG availability, and acquisition errors in the logs. An empty dispersion archive requires review and produces exit code 1 even if the dataset is not expected to contain dispersion data. Warnings are displayed for review. These checks do not certify scientific correctness, completeness against an external inventory, or the freshness of every plot: open the report and review its dates, contents, and plots before re-enabling the scheduler.

## Logs and known issues

Each session is saved under `LS_installation_scripts/local/session-*`, which is excluded from Git. Do not delete it: it contains the QC archive backup. `local/session` points to the latest session. Do not rerun `01_backup.sh` to resume an interrupted step: subsequent steps reuse the existing session.

To follow execution from a second terminal, from the repository root:

```bash
tail -f "$(cat LS_installation_scripts/local/session)/run.log"
```

Send at least `commit.txt`, `preflight.log`, `inputs.log`, `run.log`, and `verification.log` to the person reviewing the update. `run.log` is overwritten on each run: copy it if you need to retain multiple attempts.

- `Invalid required QC fields` / `remains open`: the monitor may exit with code 0 while leaving days incomplete. Do not replace `nan` values with zero. Rebuilding does not fix these inputs.
- Missing dispersion data: the examined main version searches for `*DSOL_PINHOLE*SOXS_FITTED_LINES.fits` under `reduced_root`. Files in a separate `qc` directory may not be discovered. Do not change `reduced_root` indiscriminately; it is also used for other products.
- Dry-run is not mandatory in this procedure: the examined version rejects WAL databases even when normal execution is possible. Do not convert the upstream database to work around this limitation.
- These scripts do not push commits, manage cron, publish to external services, or automatically modify the configuration. The monitor writes to the configured destinations, which may already be visible on the web.
