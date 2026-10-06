"""P0-A: observable CLI/API dry-run contracts, before the H1 correction."""
import pytest

from qc_monitor.main import consolidate
from conftest import database_snapshot, require, rows, tree_snapshot


def dry_run(lab, interface):
    if interface == "cli":
        lab.cli("--dry-run")
    else:
        selected = consolidate(lab.upstream, lab.config, dry_run=True)
        require(selected == 1, "Synthetic QC row was not selected by the API")


@pytest.mark.parametrize("interface", ["cli", "api"])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-A: dry-run creates an absent QC database and its parent")
def test_dry_run_absent_database_creates_nothing(lab, interface):
    before = tree_snapshot(lab.root)
    dry_run(lab, interface)
    assert not lab.db.exists(), "P0-A: dry-run created the QC database"
    assert not lab.db.parent.exists(), "P0-A: dry-run created the monitor directory"
    assert tree_snapshot(lab.root) == before


@pytest.mark.parametrize("interface", ["cli", "api"])
@pytest.mark.parametrize("legacy", [False, pytest.param(True, marks=pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="P0-A: dry-run migrates an existing schema"))],
    ids=["current-schema", "migration-needed"])
def test_dry_run_existing_database_is_unchanged(lab, interface, legacy):
    lab.seed(legacy=legacy)
    before_sql = database_snapshot(lab.db)
    before_files = tree_snapshot(lab.root)
    dry_run(lab, interface)
    assert database_snapshot(lab.db) == before_sql, "P0-A: dry-run changed data or schema"
    assert tree_snapshot(lab.root) == before_files, "P0-A: dry-run modified database files"


@pytest.mark.parametrize("existing", [False, True], ids=["absent-db", "existing-db"])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="P0-A: dry-run/rebuild is accepted and changes the archive")
def test_dry_run_rebuild_is_rejected_without_side_effects(lab, existing):
    if existing:
        lab.seed()
    before_files = tree_snapshot(lab.root)
    before_sql = database_snapshot(lab.db) if existing else None
    result = lab.cli("--dry-run", "--rebuild-db", expected=None)
    require(result.returncode in (0, 2), f"Unexpected CLI failure: {result.stderr}")
    # Check destructive effects first so the baseline's deletion is explicit.
    assert tree_snapshot(lab.root) == before_files, "P0-A: incompatible flags changed files"
    if existing:
        assert database_snapshot(lab.db) == before_sql
    assert result.returncode == 2, "P0-A: CLI accepted incompatible dry-run/rebuild flags"


@pytest.mark.parametrize("interface", ["cli", "api"])
@pytest.mark.parametrize("existing_output", [False, True], ids=["absent-output", "existing-output"])
def test_dry_run_preserves_inputs_and_report(lab, interface, existing_output):
    lab.dsol()
    lab.oloc()
    lab.detlin()
    lab.cfg["plots"].update(
        datapoint_queries={"bias": {"filters": {"qc_name": "bias_level"}}},
        figures=[{"name": "vis_bias", "type": "time_series", "title": "Synthetic bias",
                  "filename": "existing.png", "time_range": "all", "y_label": "ADU",
                  "series": [{"label": "VIS", "style": "markers", "datapoint_query": "bias"}]}],
    )
    lab.save_config()
    if existing_output:
        lab.publish_sentinels()
    input_roots = (lab.upstream.parent, lab.reduced, lab.raw, lab.config.parent)
    before_inputs = [tree_snapshot(root) for root in input_roots]
    before_output = tree_snapshot(lab.output)
    dry_run(lab, interface)
    assert [tree_snapshot(root) for root in input_roots] == before_inputs
    assert tree_snapshot(lab.output) == before_output


@pytest.mark.parametrize("interface", ["cli", "api"])
def test_ordinary_consolidation_persists_data(lab, interface):
    if interface == "cli":
        lab.cli("--no-plots")
    else:
        assert consolidate(lab.upstream, lab.config) == 1
    assert rows(lab.db, 'SELECT qc_name, qc_value FROM qc_metrics') == [("bias_level", 100.0)]
    assert rows(lab.db, 'SELECT obs_day, status FROM processed_obs_days') == [("2026-10-05", "PROCESSED")]


def test_ordinary_rebuild_replaces_sentinels(lab):
    lab.seed()
    lab.cli("--rebuild-db", "--no-plots")
    assert rows(lab.db, 'SELECT qc_name FROM qc_metrics') == [("bias_level",)]
    assert rows(lab.db, 'SELECT obs_day FROM processed_obs_days') == [("2026-10-05",)]
