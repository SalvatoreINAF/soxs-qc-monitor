"""Compatible plotting interface; dispatch is declared in the lightweight registry."""
import pandas as pd
from pathlib import Path
from .figure_result import FigureResult
from ._plots_common import (
    InvalidPlotData,
    PROCESSING_FUNCTIONS,
    PlotSeries,
    SeriesStyle,
    _apply_filters,
    _apply_processing,
    _apply_time_range,
    _attempt,
    _latest_time_rows,
    _normalize_order_label,
    _prepare_scalar_series,
    _prepare_xy,
    _renderer,
    _require_columns,
    _save_figure,
    _series_from_config,
    _style_to_matplotlib,
    _valid_rows,
    log,
    process_none,
    resolve_datapoint_query,
)
from ._plots_qc import (
    plot_histogram_from_config,
    plot_latest_by_order_from_config,
    plot_time_series,
    plot_time_series_from_config,
    plot_xy_scatter_from_config,
)
from ._plots_dsol import (
    plot_dispersion_residual_histogram_from_config,
    plot_dispersion_residual_xy_from_config,
    plot_dispersion_resolution_from_config,
    plot_dispersion_resolution_timeseries_from_config,
)
from ._plots_oloc import (
    _evaluate_order_xy_polynomial,
    _extract_poly_coefficients,
    _select_latest_oloc,
    plot_order_location_fit_from_config,
)
from ._plots_detlin import (
    plot_detector_linearity_from_config,
    select_detector_linearity_sequences,
)
from ._renderers import RENDERERS


def plot_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    datapoint_queries: dict,
    output_dir: Path,
    show: bool = False,
):
    plot_type = plot_cfg.get("type")
    spec = RENDERERS.get(plot_type) if isinstance(plot_type, str) else None
    if spec is None or spec.dataset == "oloc":
        raise ValueError(f"Unsupported plot type: {plot_type}")
    return spec.render((df,), plot_cfg, datapoint_queries, output_dir, show)


def _render_configured(figures, render, continue_on_error):
    results = []
    for config in figures:
        try:
            results.append(render(config))
        except Exception as exc:
            if not continue_on_error:
                raise
            log.exception('Figure %s failed', config.get('name'))
            code = 'invalid_data' if isinstance(exc, (InvalidPlotData, KeyError)) else 'render_error'
            results.append(FigureResult.failed(config, exc, code))
    return results


def generate_plots_from_config(
    df: pd.DataFrame,
    plots_cfg: dict,
    plot_types: set[str] | None = None,
    *, continue_on_error: bool = False,
):
    figures = [config for config in plots_cfg.get('figures', [])
               if plot_types is None or config.get('type') in plot_types]
    return _render_configured(figures, lambda config: plot_from_config(
        df, config, plots_cfg.get('datapoint_queries', {}),
        Path(plots_cfg.get('output_dir', 'plots')), bool(plots_cfg.get('show', False))),
        continue_on_error)


def generate_order_location_plots_from_config(
    df_models: pd.DataFrame,
    df_meta: pd.DataFrame,
    plots_cfg: dict,
    *, continue_on_error: bool = False,
):
    figures = [config for config in plots_cfg.get('figures', [])
               if config.get('type') == 'order_location_fit']
    return _render_configured(figures, lambda config: RENDERERS['order_location_fit'].render(
        (df_models, df_meta), config, plots_cfg.get('datapoint_queries', {}),
        Path(plots_cfg.get('output_dir', 'plots')), bool(plots_cfg.get('show', False))), continue_on_error)
