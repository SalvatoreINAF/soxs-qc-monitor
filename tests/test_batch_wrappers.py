"""Real tcsh wrappers, process timeout, safe retention and external freshness checks."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qc_batch", REPO / "scripts/batch.py")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


@pytest.mark.parametrize("code", [0, 1, 2])
def test_tcsh_wrapper_uses_requested_python_and_propagates_exit(tmp_path, code):
    root = tmp_path / "project with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "qc_monitor").mkdir()
    (root / "configs").mkdir()
    shutil.copyfile(REPO / "scripts/batch.py", root / "scripts/batch.py")
    shutil.copyfile(REPO / "run_SOXS_QC_Monitor.sh", root / "run_SOXS_QC_Monitor.sh")
    (root / "qc_monitor/__init__.py").write_text("")
    (root / "qc_monitor/main.py").write_text("import sys\nprint('interpreter=' + sys.executable)\nsys.exit(" + str(code) + ")\n")
    env = dict(os.environ, QC_PYTHON=sys.executable)
    result = subprocess.run(["tcsh", str(root / "run_SOXS_QC_Monitor.sh")], env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == code, result.stderr
    logs = list((root / "logs").glob("*.log"))
    assert len(logs) == 1
    log = logs[0].read_text()
    assert "interpreter=" + sys.executable in log
    assert {0: "completed", 1: "partial", 2: "blocking error"}[code] in log


def test_update_wrapper_is_wired_to_same_interpreter(tmp_path):
    # Do not perform an actual pull/install in a test. Observe wrapper dispatch only.
    capture = tmp_path / "capture.json"
    executable = tmp_path / "interpreter"
    executable.write_text("#!" + sys.executable + "\nimport json, sys\nfrom pathlib import Path\nPath(" + repr(str(capture)) + ").write_text(json.dumps(sys.argv[1:]))\nsys.exit(1)\n")
    executable.chmod(0o755)
    env = dict(os.environ, QC_PYTHON=str(executable))
    result = subprocess.run(["tcsh", str(REPO / "update_QC_Monitor.sh")], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    args = json.loads(capture.read_text())
    assert Path(args[0]) == REPO / "scripts/batch.py"
    assert args[1:] == ["update", "--root", str(REPO)]


def test_timeout_terminates_real_job(tmp_path):
    log = tmp_path / "job.log"
    with log.open("w") as stream:
        with pytest.raises(subprocess.TimeoutExpired):
            batch.execute([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, stream, time.monotonic() + 0.2)


def test_retention_protects_current_foreign_backup_and_symlink(tmp_path):
    names = ["qc_monitor_20200101T000000Z_1234abcd.log", "qc_monitor_update_20200101T000000Z_1234abcd.log",
             "qc_monitor_20200101T000000Z_deadbeef.log", "foreign.log", "qc_monitor_unrecognized.log"]
    for name in names:
        path = tmp_path / name
        path.write_text("sentinel")
        os.utime(path, (0, 0))
    current = tmp_path / names[2]
    link = tmp_path / "qc_monitor_20200101T000000Z_00000000.log"
    link.symlink_to(tmp_path / "foreign.log")
    (tmp_path / "backup_old").mkdir()
    batch.clean_logs(tmp_path, current, 30)
    assert not (tmp_path / names[0]).exists()
    assert not (tmp_path / names[1]).exists()
    assert current.exists() and link.is_symlink()
    assert (tmp_path / "foreign.log").exists() and (tmp_path / "backup_old").is_dir()


@pytest.mark.parametrize("age,code,expected", [(1, 0, 0), (1, 1, 1), (1, 2, 2), (49, 0, 2)])
def test_freshness_separates_last_run_from_data_age(tmp_path, age, code, expected):
    from datetime import datetime, timedelta, timezone
    value = {"mode": "run", "ended_utc": (datetime.now(timezone.utc) - timedelta(hours=age)).isoformat(), "exit_code": code}
    (tmp_path / "qc_monitor_20261008T000000Z_1234abcd.log").write_text("INFO:RUN_SUMMARY " + json.dumps(value) + "\n")
    assert batch.freshness(tmp_path, 48) == expected


def test_recent_missing_summary_is_not_masked_by_previous_success(tmp_path):
    from datetime import datetime, timezone
    old = tmp_path / "qc_monitor_20261007T000000Z_1234abcd.log"
    old.write_text("RUN_SUMMARY " + json.dumps({"mode": "run", "ended_utc": datetime.now(timezone.utc).isoformat(), "exit_code": 0}))
    os.utime(old, (1, 1))
    (tmp_path / "qc_monitor_20261008T000000Z_deadbeef.log").write_text("Batch supervisor failed: TimeoutExpired\n")
    assert batch.freshness(tmp_path, 48) == 2


def test_supervisor_failure_dominates_successful_monitor_summary(tmp_path):
    from datetime import datetime, timezone
    value = {"mode": "run", "ended_utc": datetime.now(timezone.utc).isoformat(), "exit_code": 0}
    (tmp_path / "qc_monitor_20261008T000000Z_1234abcd.log").write_text("RUN_SUMMARY " + json.dumps(value) + "\nBATCH_EXIT_CODE 2\n")
    assert batch.freshness(tmp_path, 48) == 2


@pytest.mark.parametrize("failure", ["git", "pip"])
def test_update_external_command_failure_is_blocking(lab, tmp_path, monkeypatch, failure):
    # Real updates are external mutations; simulate failure at their explicit boundary.
    monkeypatch.setenv("QC_MONITOR_ROOT", str(tmp_path))
    monkeypatch.setenv("MPLBACKEND", "Agg")
    monkeypatch.setattr(batch, "backup", lambda *args: None)
    shutil.copyfile(lab.config, lab.config.parent / 'qc_monitor.yaml')
    calls = []
    def fail_command(command, root, stream, deadline, **kwargs):
        calls.append(command)
        return 1 if (command[0] == "git" if failure == "git" else command[:3] == [sys.executable, "-m", "pip"]) else 0
    monkeypatch.setattr(batch, "execute", fail_command)
    assert batch.main(["update", "--root", str(lab.root)]) == 2
    assert not any(command[:3] == [sys.executable, "-m", "qc_monitor.main"] for command in calls)
