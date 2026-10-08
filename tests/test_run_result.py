"""D1 contracts: JSON diagnostics, real SQL errors and immutable inspection."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import uuid

import pytest

from conftest import DAY, database_snapshot, rows, tree_snapshot
from qc_monitor.main import _consolidate_qc_sources
from qc_monitor.storage import SQLiteStore


def summary(result):
    lines = [line.split("RUN_SUMMARY ", 1)[1] for line in result.stderr.splitlines() if "RUN_SUMMARY " in line]
    assert len(lines) == 1, result.stderr
    value = json.loads(lines[0])
    assert value["format_version"] == 1
    uuid.UUID(value["run_id"])
    assert value["exit_code"] == result.returncode
    assert value["duration_seconds"] >= 0
    assert value["started_utc"].endswith("+00:00")
    assert value["ended_utc"] >= value["started_utc"]
    return value


def execute(path, query):
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(query)
        conn.commit()


def test_summary_saved_and_closed_day_counts(lab):
    lab.dsol()
    lab.oloc()
    lab.detlin()
    target = lab.root / "summaries/run.json"
    first = summary(lab.cli("--no-plots", "--summary-json", str(target)))
    assert json.loads(target.read_text()) == first
    qc = first["families"]["qc"]
    assert qc["completed_units"] == [[DAY]]
    assert qc["tables"]["qc_metrics"]["persisted"] == 1
    assert qc["latest_data_utc"] == DAY + "T08:00:00"
    second = summary(lab.cli("--no-plots"))
    for name, family in second["families"].items():
        assert family["skipped_units"], name
        assert all(table["selected"] == table["persisted"] == 0 for table in family["tables"].values())
        assert all(table["preserved"] > 0 for table in family["tables"].values())
    assert first["run_id"] != second["run_id"]


@pytest.mark.parametrize("mode", ["--dry-run", "--preflight"])
@pytest.mark.parametrize("existing", [False, True])
def test_inspection_summary_is_log_only(lab, mode, existing):
    if existing:
        lab.seed()
    target = lab.root / "new/summary.json"
    before = tree_snapshot(lab.root)
    value = summary(lab.cli(mode, "--summary-json", str(target)))
    assert value["mode"] == mode[2:]
    assert tree_snapshot(lab.root) == before
    assert not target.exists()
    if mode == "--dry-run":
        assert value["families"]["qc"]["completed_units"] == []
        assert value["families"]["qc"]["validated_units"] == [[DAY]]


@pytest.mark.parametrize("failed", [False, True])
def test_empty_vs_failure_and_independent_family(lab, failed):
    execute(lab.upstream, "DROP TABLE quality_control_plus_lite" if failed else "DELETE FROM quality_control_plus_lite")
    lab.dsol()
    value = summary(lab.cli("--no-plots", expected=1 if failed else 0))
    family = value["families"]["qc"]
    assert family["state"] == ("partial" if failed else "no_data")
    assert bool(family["errors"]) == failed
    assert value["families"]["dsol"]["completed_units"] == [[DAY]]
    assert value["families"]["detlin"]["state"] == "disabled"


def test_incomplete_retry_and_deduplication_counts(lab):
    execute(lab.upstream, 'INSERT INTO quality_control_plus_lite SELECT * FROM quality_control_plus_lite')
    execute(lab.upstream, 'INSERT INTO quality_control_plus_lite SELECT * FROM quality_control_plus_lite LIMIT 1')
    execute(lab.upstream, "UPDATE quality_control_plus_lite SET qc_value='invalid' WHERE rowid=3")
    value = summary(lab.cli("--no-plots", expected=1))
    table = value["families"]["qc"]["tables"]["qc_metrics"]
    assert table["selected"] == table["not_persisted_incomplete"] == 2
    assert table["discarded"] == 1
    assert table["persisted"] == 0
    execute(lab.upstream, "UPDATE quality_control_plus_lite SET qc_value=100 WHERE rowid=3")
    table = summary(lab.cli("--no-plots"))["families"]["qc"]["tables"]["qc_metrics"]
    assert table["selected"] == 3
    assert table["duplicates"] == 2
    assert table["persisted"] == 1


@pytest.mark.parametrize("kind", ["configuration", "summary", "plot"])
def test_blocking_error_produces_summary(lab, kind):
    if kind == "configuration":
        lab.config.write_text("[malformed")
        args = ["--no-plots"]
    elif kind == "summary":
        args = ["--no-plots", "--summary-json", str(lab.root)]
    else:
        lab.cfg["plots"]["figures"] = [{"name": "missing", "type": "time_series", "filename": "missing.png",
            "title": "missing", "series": [{"datapoint_query": "unknown", "label": "unknown"}]}]
        lab.save_config()
        args = []
    value = summary(lab.cli(*args, expected=2))
    assert value["errors"]
    assert "Traceback" in lab.cli(*args, expected=2).stderr
    if kind == "summary":
        assert not list(lab.root.glob(".qc-summary-*"))


def test_real_database_lock_keeps_transaction_and_retry(lab):
    store = SQLiteStore(lab.db)
    before = database_snapshot(lab.db)
    with closing(sqlite3.connect(lab.db)) as holder:
        holder.execute("BEGIN EXCLUSIVE")
        value = summary(lab.cli("--no-plots", expected=2))
        assert value["errors"][0]["type"] == "OperationalError"
        holder.rollback()
    assert database_snapshot(lab.db) == before
    summary(lab.cli("--no-plots"))
    assert rows(lab.db, "SELECT count(*) FROM qc_metrics") == [(1,)]


def test_sql_failure_counters_advance_only_after_commit(lab):
    store = SQLiteStore(lab.db)
    execute(lab.db, "CREATE TRIGGER stop BEFORE INSERT ON processed_obs_days BEGIN SELECT RAISE(ABORT, 'stop'); END")
    report = {}
    with pytest.raises(sqlite3.IntegrityError):
        _consolidate_qc_sources([lab.upstream], lab.cfg, store, counts=report)
    assert report["tables"]["qc_metrics"]["persisted"] == 0
    assert report["completed_units"] == []
    assert rows(lab.db, "SELECT count(*) FROM qc_metrics") == [(0,)]


@pytest.mark.parametrize("destination", ["upstream", "db", "config"])
def test_summary_cannot_overwrite_inputs_or_database(lab, destination):
    lab.seed()
    target = {"upstream": lab.upstream, "db": lab.db, "config": lab.config}[destination]
    before = tree_snapshot(lab.root)
    value = summary(lab.cli("--no-plots", "--summary-json", str(target), expected=2))
    assert "overlaps" in value["errors"][0]["reason"]
    assert tree_snapshot(lab.root) == before


def test_malformed_config_cannot_be_replaced_by_summary(lab):
    lab.config.write_text("[malformed")
    before = tree_snapshot(lab.root)
    summary(lab.cli("--summary-json", str(lab.config), expected=2))
    assert tree_snapshot(lab.root) == before
