"""Analytical expectations and representative rendering, without pixel snapshots."""
from html.parser import HTMLParser
from pathlib import Path
import importlib.util
import sys

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from qc_monitor.main import (consolidate_dispersion_solution, consolidate_order_location_models,
                             consolidate_detector_linearity, load_config, default_config_path,
                             ConfigurationError)
from qc_monitor.plotting import (_evaluate_order_xy_polynomial, generate_plots_from_config,
                                 generate_order_location_plots_from_config, resolve_datapoint_query)
from qc_monitor.generate_html import generate_html_report
from qc_monitor.storage import SQLiteStore
from conftest import DAY


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []
    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.sources.append(dict(attrs)["src"])


def test_polynomial_has_independent_analytical_expectation():
    orders = np.array([2., 3.])
    y = np.array([5., 7.])
    # f(o,y) = 1 + 2y + 3o + 4oy; asymmetric coordinates detect coefficient ordering.
    expected = np.array([57., 108.])
    assert _evaluate_order_xy_polynomial(orders, y, [1., 2., 3., 4.], 1, 1) == pytest.approx(expected, rel=1e-10, abs=1e-8)


def test_config_includes_duplicates_and_environment_root(tmp_path, monkeypatch):
    config = tmp_path / "configs/qc_monitor.yaml"
    config.parent.mkdir()
    included = config.parent / "plots.yaml"
    included.write_text("datapoint_queries: {sample: {filters: {}}}\nfigures: [{name: included}]\n")
    config.write_text("plots: {include: [plots.yaml]}\n")
    from qc_monitor.config import load_plot_includes
    cfg = load_plot_includes({'plots': {'include': ['plots.yaml']}}, config.parent)
    assert cfg["plots"]["figures"] == [{"name": "included"}]
    monkeypatch.setenv("QC_MONITOR_ROOT", str(tmp_path))
    assert default_config_path() == config
    config.write_text("plots: {include: [plots.yaml], datapoint_queries: {sample: {}}}\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_config(config)
    config.unlink()
    with pytest.raises(ConfigurationError, match="QC_MONITOR_ROOT"):
        default_config_path()


def test_unknown_query_is_explicit():
    with pytest.raises(ValueError, match="Datapoint query not found"):
        resolve_datapoint_query(pd.DataFrame(), "unknown", {})


def representative_report(lab, output):
    lab.dsol()
    oloc = lab.oloc()
    from astropy.io import fits
    from astropy.table import Table
    with fits.open(oloc, mode="update") as hdul:
        model = Table(hdul[1].data)
        for prefix, value in (("edgelow", 1.), ("edgeup", 3.)):
            model["degorder_" + prefix] = [0]
            model["degy_" + prefix] = [0]
            model[prefix + "_c00"] = [value]
        hdul[1] = fits.BinTableHDU(model)
    lab.detlin(times=(1, 2, 3))
    store = SQLiteStore(lab.db)
    consolidate_dispersion_solution(lab.reduced, store)
    consolidate_order_location_models(lab.reduced, store)
    consolidate_detector_linearity(lab.cfg, store)
    metrics = pd.DataFrame({"night start date": ["2026-10-03", "2026-10-04", DAY],
        "obs_date_utc": [DAY + "T08:00:00", DAY + "T09:00:00", DAY + "T10:00:00"],
        "qc_value": [100., 110., 90.], "qc_order": [10, 11, 12], "eso seq arm": ["VIS"] * 3})
    lines = store.load_dispersion_solution_lines()
    lines["residuals_x"] = [0.1, -0.2]
    lines["residuals_y"] = [-0.1, 0.2]
    lines["x_diff"] = [0.1, -0.2]
    lines["y_diff"] = [-0.1, 0.2]
    lines["residuals_xy"] = np.hypot(lines.x_diff, lines.y_diff)
    stats = store.load_dispersion_resolution_stats()
    assert stats.mean_R_pin.iloc[0] == pytest.approx(1100., rel=1e-10, abs=1e-8)
    assert stats.std_R_pin.iloc[0] == pytest.approx(np.sqrt(20000.), rel=1e-10, abs=1e-8)
    figures = []
    types = ("time_series", "xy_scatter", "histogram", "latest_by_order_bar", "dispersion_resolution",
             "dispersion_resolution_timeseries", "dispersion_residual_xy", "dispersion_residual_histogram",
             "order_location_fit", "detector_linearity")
    for kind in types:
        figure = {"name": "vis_" + kind, "title": "VIS " + kind.replace("_", " "),
                  "type": kind, "filename": kind + ".png", "arm": "VIS", "selection": "all",
                  "datapoint_query": "sample", "series": [{"datapoint_query": "sample", "label": "Synthetic"}],
                  "x": {"datapoint_query": "sample"}, "y": {"datapoint_query": "sample"}, "axis_b_step": 1}
        if kind == "order_location_fit":
            figure["selection"] = "latest"
        figures.append(figure)
    # Both report tabs are exercised with a NIR trend and detector-linearity fit.
    nir_fig = dict(figures[0], name="nir_trend", title="NIR trend", filename="nir_trend.png", arm="NIR")
    figures.append(nir_fig)
    lab.detlin(arm="NIR", times=(1, 2, 3))
    consolidate_detector_linearity(lab.cfg, store)
    figures.append(dict(figures[-2], name="nir_detlin", title="NIR detector linearity",
                        type="detector_linearity", filename="nir_detlin.png", arm="NIR", mode_order=["NIR"]))
    cfg = {"figures": figures, "output_dir": str(output / "plots"), "show": False,
           "datapoint_queries": {"sample": {"filters": {}}}}
    generate_plots_from_config(metrics, cfg, {"time_series", "xy_scatter", "histogram", "latest_by_order_bar"})
    generate_plots_from_config(lines, cfg, {"dispersion_resolution", "dispersion_residual_xy", "dispersion_residual_histogram"})
    generate_plots_from_config(stats, cfg, {"dispersion_resolution_timeseries"})
    generate_order_location_plots_from_config(store.load_order_location_models(), store.load_order_location_meta(), cfg)
    generate_plots_from_config(store.load_detector_linearity_results(), cfg, {"detector_linearity"})
    generate_html_report(cfg, output / "index.html")
    return cfg


def test_all_rendering_families_and_html_references(lab):
    cfg = representative_report(lab, lab.output)
    parser = Images()
    parser.feed((lab.output / "index.html").read_text())
    assert len(parser.sources) == len(cfg["figures"])
    for source in parser.sources:
        path = lab.output / source
        assert path.is_file(), source
        image = mpimg.imread(path)
        assert image.shape[0] > 100 and image.shape[1] > 100
        assert np.std(image[..., :3]) > 0.01
    assert plt.get_fignums() == []


def test_empty_figure_is_normal(lab):
    cfg = {"output_dir": str(lab.output / "plots"), "figures": [{"type": "time_series", "name": "empty",
        "filename": "empty.png", "series": [{"datapoint_query": "sample", "label": "empty"}]}],
        "datapoint_queries": {"sample": {"filters": {}}}}
    generate_plots_from_config(pd.DataFrame(), cfg)
    assert not (lab.output / "plots/empty.png").exists()


def test_save_failure_is_not_silently_accepted(lab):
    blocked = lab.root / "blocked"
    blocked.write_text("not a directory")
    cfg = {"output_dir": str(blocked), "figures": [{"type": "histogram", "name": "failure",
        "filename": "test.png", "datapoint_query": "sample"}], "datapoint_queries": {"sample": {"filters": {}}}}
    try:
        with pytest.raises(OSError):
            generate_plots_from_config(pd.DataFrame({"obs_date_utc": [DAY], "qc_value": [1.]}), cfg)
    finally:
        # Guaranteed renderer cleanup on exceptions is D3, not silently claimed here.
        plt.close("all")


def test_standalone_default_and_explicit_threshold(lab):
    path = Path(__file__).resolve().parents[1] / "utils/analyze_detector_linearity.py"
    spec = importlib.util.spec_from_file_location("d1_standalone", path)
    standalone = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = standalone
    spec.loader.exec_module(standalone)
    standalone.load_libraries()
    lab.detlin()
    del lab.cfg["detector_linearity"]["saturation_fraction"]
    lab.save_config()
    _, _, level, threshold = standalone.load_config(lab.config)
    assert threshold == pytest.approx(0.60 * level)
    lab.cfg["detector_linearity"]["saturation_fraction"] = 0.25
    lab.save_config()
    _, _, level, threshold = standalone.load_config(lab.config)
    assert threshold == pytest.approx(0.25 * level)


def test_fit_threshold_boundary_and_independent_line():
    from qc_monitor.detector_linearity import _fit_detector_linearity_rows
    # y=10t+5 for the usable points; third point tests exclusion above the exact boundary.
    points = [{"exptime": 1., "signal": 15.}, {"exptime": 2., "signal": 25.},
              {"exptime": 3., "signal": 25.00001}]
    _fit_detector_linearity_rows(points, 25.)
    assert [row["fit_used"] for row in points] == [1, 1, 0]
    assert [row["slope"] for row in points] == pytest.approx([10.] * 3, rel=1e-10, abs=1e-8)
    assert [row["intercept"] for row in points] == pytest.approx([5.] * 3, rel=1e-10, abs=1e-8)
    assert points[2]["fit_signal"] == pytest.approx(35., rel=1e-10, abs=1e-8)
