"""Static renderer registry with lazy, explicitly coded family adapters.

Importing this module never imports Matplotlib. Configuration cannot name Python
modules or functions: only the ten keys declared below are accepted.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RendererSpec:
    dataset: str
    render: Callable


def _time_series(frames, config, queries, output_dir, show):
    from ._plots_qc import plot_time_series_from_config
    return plot_time_series_from_config(frames[0], config, queries, output_dir, show)


def _xy_scatter(frames, config, queries, output_dir, show):
    from ._plots_qc import plot_xy_scatter_from_config
    return plot_xy_scatter_from_config(frames[0], config, queries, output_dir, show)


def _histogram(frames, config, queries, output_dir, show):
    from ._plots_qc import plot_histogram_from_config
    return plot_histogram_from_config(frames[0], config, queries, output_dir, show)


def _latest_by_order_bar(frames, config, queries, output_dir, show):
    from ._plots_qc import plot_latest_by_order_from_config
    return plot_latest_by_order_from_config(frames[0], config, queries, output_dir, show)


def _dispersion_resolution(frames, config, queries, output_dir, show):
    from ._plots_dsol import plot_dispersion_resolution_from_config
    return plot_dispersion_resolution_from_config(frames[0], config, output_dir, show)


def _dispersion_residual_xy(frames, config, queries, output_dir, show):
    from ._plots_dsol import plot_dispersion_residual_xy_from_config
    return plot_dispersion_residual_xy_from_config(frames[0], config, output_dir, show)


def _dispersion_residual_histogram(frames, config, queries, output_dir, show):
    from ._plots_dsol import plot_dispersion_residual_histogram_from_config
    return plot_dispersion_residual_histogram_from_config(frames[0], config, output_dir, show)


def _dispersion_resolution_timeseries(frames, config, queries, output_dir, show):
    from ._plots_dsol import plot_dispersion_resolution_timeseries_from_config
    return plot_dispersion_resolution_timeseries_from_config(frames[0], config, output_dir, show)


def _order_location_fit(frames, config, queries, output_dir, show):
    from ._plots_oloc import plot_order_location_fit_from_config
    return plot_order_location_fit_from_config(frames[0], frames[1], config, output_dir, show)


def _detector_linearity(frames, config, queries, output_dir, show):
    from ._plots_detlin import plot_detector_linearity_from_config
    return plot_detector_linearity_from_config(frames[0], config, output_dir, show)


RENDERERS = {
    'time_series': RendererSpec('qc', _time_series),
    'xy_scatter': RendererSpec('qc', _xy_scatter),
    'histogram': RendererSpec('qc', _histogram),
    'latest_by_order_bar': RendererSpec('qc', _latest_by_order_bar),
    'dispersion_resolution': RendererSpec('dsol_lines', _dispersion_resolution),
    'dispersion_residual_xy': RendererSpec('dsol_lines', _dispersion_residual_xy),
    'dispersion_residual_histogram': RendererSpec('dsol_lines', _dispersion_residual_histogram),
    'dispersion_resolution_timeseries': RendererSpec('dsol_stats', _dispersion_resolution_timeseries),
    'order_location_fit': RendererSpec('oloc', _order_location_fit),
    'detector_linearity': RendererSpec('detlin', _detector_linearity),
}


def types_for_dataset(dataset):
    return {kind for kind, spec in RENDERERS.items() if spec.dataset == dataset}
