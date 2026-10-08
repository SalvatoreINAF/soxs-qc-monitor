#!/usr/bin/env python3
"""Batch supervision using the same interpreter as installation and execution."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

LOG_PATTERN = re.compile(r"qc_monitor_(?:update_)?\d{8}T\d{6}Z(?:_[0-9a-f]{8})?\.log$")


def clean_logs(directory, current, days):
    cutoff = time.time() - days * 86400
    for path in directory.iterdir():
        if LOG_PATTERN.fullmatch(path.name) and path != current and not path.is_symlink() and path.is_file():
            if path.stat().st_mtime < cutoff:
                path.unlink()


def freshness(directory, hours):
    """Detect missing/failed jobs; data age is intentionally a separate concern."""
    latest = None
    supervisor_code = 0
    attempts = [path for path in directory.glob("qc_monitor_*.log")
                if LOG_PATTERN.fullmatch(path.name) and not path.name.startswith("qc_monitor_update_")
                and not path.is_symlink() and path.is_file()]
    # A new timed-out attempt with no summary must not be hidden by an older success.
    attempts = sorted(attempts, key=lambda path: path.stat().st_mtime_ns, reverse=True)[:1]
    for path in attempts:
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith("BATCH_EXIT_CODE "):
                try:
                    supervisor_code = int(line.split()[1])
                    if supervisor_code not in (0, 1, 2):
                        supervisor_code = 2
                except (ValueError, IndexError):
                    supervisor_code = 2
            if "RUN_SUMMARY " not in line:
                continue
            try:
                value = json.loads(line.split("RUN_SUMMARY ", 1)[1])
                if value["mode"] != "run" or value.get("exit_code") not in (0, 1, 2):
                    continue
                ended = datetime.fromisoformat(value["ended_utc"])
                if ended.tzinfo is None:
                    continue
                if latest is None or ended > latest[0]:
                    latest = (ended, value)
            except (ValueError, KeyError, TypeError):
                continue
    if latest is None or (datetime.now(timezone.utc) - latest[0]).total_seconds() > hours * 3600:
        print("No recent batch summary")
        return 2
    print(f"Latest batch: {latest[0].isoformat()}, exit {latest[1]['exit_code']}")
    return max(supervisor_code, int(latest[1]["exit_code"]))


def execute(command, root, stream, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command, 0)
    # A separate process group allows termination of the whole job on timeout.
    with subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
                          start_new_session=True) as process:
        try:
            return process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise


def backup(root, directory, stream, deadline):
    """Preserve config, Git revision, environment and a consistent SQLite snapshot."""
    directory.mkdir()
    shutil.copytree(root / "configs", directory / "configs")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=max(0.01, deadline - time.monotonic()))
    (directory / "revision.txt").write_text(revision)
    with (directory / "requirements.txt").open("w") as output:
        subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=output, check=True, timeout=max(0.01, deadline - time.monotonic()))
    # YAML is an existing runtime dependency, not needed for batch supervision.
    import yaml
    cfg = yaml.safe_load((root / "configs/qc_monitor.yaml").read_text())
    database = Path(cfg["paths"]["qc_database"]).expanduser()
    if not database.is_absolute():
        database = root / database
    if database.exists():
        from contextlib import closing
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(directory / "qc.sqlite")) as destination:
                def progress(status, remaining, total):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Database backup exceeded job timeout")
                source.backup(destination, pages=256, progress=progress, sleep=0.1)
    stream.write(f"Backup: {directory}\n")
    stream.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "update", "freshness"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("QC_JOB_TIMEOUT_SECONDS", 7200)))
    parser.add_argument("--log-days", type=float, default=float(os.environ.get("QC_LOG_RETENTION_DAYS", 30)))
    parser.add_argument("--freshness-hours", type=float, default=float(os.environ.get("QC_FRESHNESS_HOURS", 48)))
    args = parser.parse_args(argv)
    if not all(0 < value < float("inf") for value in (args.timeout, args.log_days, args.freshness_hours)):
        parser.error("time limits must be finite and positive")
    root = args.root.expanduser().resolve()
    logs = root / "logs"
    if args.action == "freshness":
        return freshness(logs, args.freshness_hours)
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    prefix = "qc_monitor_update_" if args.action == "update" else "qc_monitor_"
    current = logs / (prefix + stamp + ".log")
    deadline = time.monotonic() + args.timeout
    os.environ["QC_MONITOR_ROOT"] = str(root)
    os.environ["MPLBACKEND"] = "Agg"
    commands = []
    cli = [sys.executable, "-m", "qc_monitor.main", "--config", str(root / "configs/qc_monitor.yaml")]
    with current.open("w", buffering=1) as stream:
        stream.write(f"UTC start: {datetime.now(timezone.utc).isoformat()}\nPython: {sys.executable}\n")
        code = 2
        try:
            if args.action == "update":
                backup(root, logs / ("backup_" + stamp), stream, deadline)
                commands.extend((["git", "pull", "--ff-only"],
                                 [sys.executable, "-m", "pip", "install", "."]))
                commands.extend((cli + ["--preflight"], cli + ["--dry-run"]))
            else:
                commands.append(cli + ["--verbose"])
            for command in commands:
                code = execute(command, root, stream, deadline)
                if code:
                    break
            # Non-CLI failures may have unrelated exit codes; batch contract is 0/1/2.
            code = code if code in (0, 1, 2) else 2
        except Exception as exc:
            stream.write(f"Batch supervisor failed: {type(exc).__name__}: {exc}\n")
            code = 2
        label = {0: "completed", 1: "partial", 2: "blocking error"}[code]
        stream.write(f"UTC end: {datetime.now(timezone.utc).isoformat()}\nBatch {label}; exit {code}\n")
    try:
        clean_logs(logs, current, args.log_days)
    except OSError as exc:
        with current.open("a") as stream:
            stream.write(f"Log cleanup failed: {exc}\n")
        code = 2
    with current.open("a") as stream:
        stream.write(f"BATCH_EXIT_CODE {code}\n")
    print(f"Batch log: {current}")
    return code


if __name__ == "__main__":
    sys.exit(main())
