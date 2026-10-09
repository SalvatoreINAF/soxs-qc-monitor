"""Shared plotting mechanics; scientific renderers live in family modules."""
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from .figure_result import FigureResult


class InvalidPlotData(ValueError):
    """Selected data cannot represent the configured figure."""


_attempt = ContextVar('figure_attempt', default=None)


def _renderer(function):
    """Collect explicit save outcomes and close only this call's figures."""
    parameters = signature(function)

    @wraps(function)
    def render(*args, **kwargs):
        bound = parameters.bind(*args, **kwargs)
        bound.apply_defaults()
        values = bound.arguments
        cfg = values.get('plot_cfg', {})
        filename = cfg.get('filename', Path(values.get('output_file', 'plot.png')).name)
        name = cfg.get('name', values.get('title', filename))
        kind = cfg.get('type', 'time_series')
        attempt = {'path': None, 'discarded': []}
        token = _attempt.set(attempt)
        previous = set(plt.get_fignums())
        try:
            data = values.get('df', values.get('df_models'))
            if data is not None and data.empty:
                return FigureResult(name, kind, filename, 'no_data', 'empty_history',
                                    'No historical data available')
            result = function(*args, **kwargs)
            if isinstance(result, FigureResult):
                result.name, result.type, result.filename = name, kind, filename
                return result
            if attempt['path'] is not None:
                return FigureResult(name, kind, filename, 'produced', 'saved',
                                    'Figure saved successfully', attempt['path'],
                                    discarded=attempt['discarded'])
            return FigureResult(name, kind, filename, 'no_data', 'empty_selection',
                                'No matching data or insufficient samples',
                                discarded=attempt['discarded'])
        finally:
            for number in set(plt.get_fignums()) - previous:
                plt.close(number)
            _attempt.reset(token)
    return render


def _require_columns(df, columns):
    missing = set(columns) - set(df.columns)
    if missing and not df.empty:
        raise InvalidPlotData('Required columns missing: ' + ', '.join(sorted(missing)))


def _valid_rows(df, columns, *, numeric=(), dates=(), series=(), context='samples'):
    """Retain the old usable-sample selection, rejecting infinities too."""
    if df.empty:
        return df.copy()
    _require_columns(df, columns)
    out = df.copy()
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors='coerce')
        out[column] = out[column].where(np.isfinite(out[column]))
    for column in dates:
        out[column] = pd.to_datetime(out[column], errors='coerce')
    valid = out.dropna(subset=list(columns)).copy()
    discarded = len(out) - len(valid)
    if discarded:
        attempt = _attempt.get()
        if attempt is not None:
            attempt['discarded'].append({'context': context, 'count': discarded,
                                         'reason': 'Invalid required values'})
    if valid.empty:
        raise InvalidPlotData(f'No usable {context}: all selected values are invalid')
    if series:
        # A known series that loses every required sample is a failed series,
        # rather than an apparently legitimate empty panel/order.
        selected_keys = set(out.dropna(subset=list(series))[list(series)].itertuples(index=False, name=None))
        valid_keys = set(valid[list(series)].itertuples(index=False, name=None))
        if selected_keys - valid_keys:
            raise InvalidPlotData(f'An entire series has invalid required values: {context}')
    return valid


def _latest_time_rows(df, column='obs_date_utc'):
    out = _valid_rows(df, [column], dates=[column], context=column)
    times = pd.to_datetime(df[column], errors='coerce')
    return df[times == out[column].max()].copy()


log = logging.getLogger("qc_monitor.plotting")


SeriesStyle = Literal["markers", "line", "line+markers"]


@dataclass
class PlotSeries:
    query_name: str
    label: str
    style: SeriesStyle = "line+markers"


def process_none(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    return df


PROCESSING_FUNCTIONS = {
    "none": process_none,
}


def _save_figure(output_path, fig=None):

    if fig is None:
        fig = plt.gcf()

    fig.savefig(
        output_path,
        dpi=250,
        bbox_inches="tight",
        pad_inches=0.05,
    )
    attempt = _attempt.get()
    if attempt is not None:
        attempt['path'] = str(Path(output_path).resolve())


def _apply_filters(df: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    out = df
    _require_columns(df, filters)
    if df.empty:
        return df.copy()

    for column, value in filters.items():

        out = out[out[column].isna() if value is None else out[column] == value]

    return out.copy()


def _apply_processing(df: pd.DataFrame, processing_cfg: dict | None) -> pd.DataFrame:
    if not processing_cfg:
        return df

    function_name = processing_cfg.get("function", "none")
    params = processing_cfg.get("params", {})

    func = PROCESSING_FUNCTIONS.get(function_name)

    if func is None:
        raise ValueError(f"Unsupported processing function: {function_name}")

    return func(df, params)


def resolve_datapoint_query(
    df: pd.DataFrame,
    query_name: str,
    datapoint_queries: dict,
) -> pd.DataFrame:
    if query_name not in datapoint_queries:
        raise ValueError(f"Datapoint query not found: {query_name}")

    query_cfg = datapoint_queries[query_name]

    out = _apply_filters(
        df,
        query_cfg.get("filters", {}),
    )

    out = _apply_processing(
        out,
        query_cfg.get("processing", {"function": "none"}),
    )

    return out.copy()


def _apply_time_range(
    df: pd.DataFrame,
    time_column: str,
    time_range: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    if time_range == "all":
        return df

    if time_range != "last_3_months":
        raise ValueError(f"Unsupported time_range: {time_range}")

    valid = _valid_rows(df, [time_column], dates=[time_column], context=time_column)
    times = pd.to_datetime(df[time_column], errors='coerce')
    max_time = valid[time_column].max()

    cutoff = max_time - pd.DateOffset(months=3)

    return df[times >= cutoff].copy()


def _style_to_matplotlib(style: SeriesStyle) -> dict[str, object]:
    if style == "markers":
        return {"marker": "o", "linestyle": "None"}

    if style == "line":
        return {"marker": None, "linestyle": "-"}

    if style == "line+markers":
        return {"marker": "o", "linestyle": "-"}

    raise ValueError(f"Unsupported series style: {style}")


def _series_from_config(series_cfg: dict) -> PlotSeries:
    return PlotSeries(
        query_name=series_cfg["datapoint_query"],
        label=series_cfg["label"],
        style=series_cfg.get("style", "line+markers"),
    )


def _prepare_xy(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
) -> pd.DataFrame:
    out = _valid_rows(df, [x_column, y_column], numeric=[y_column],
                      dates=[x_column], context=f'{x_column}/{y_column}')
    out['_x'], out['_y'] = out[x_column], out[y_column]
    return out.sort_values('_x')


def _normalize_order_label(value: object) -> str:
    """
    Normalize qc_order labels.

    VIS orders are already strings: u, g, r, i.
    NIR orders may arrive as 10.0, 11.0, etc. and should become 10, 11, etc.
    """
    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    return text


def _prepare_scalar_series(
    df: pd.DataFrame,
    value_column: str,
    join_column: str,
) -> pd.DataFrame:
    out = _valid_rows(df, [join_column, value_column], numeric=[value_column],
                      context=f'{join_column}/{value_column}')
    if out.empty:
        return pd.DataFrame(columns=[join_column, '_value'])
    out['_value'] = out[value_column]

    # If multiple rows exist for the same observing day, average them.
    # This keeps xy plots well-defined without requiring identical sampling.
    out = (
        out.groupby(join_column, as_index=False)["_value"]
        .mean()
    )

    return out


def _select_dispersion_rows(frame, selection):
    if selection == "latest":
        return _latest_time_rows(frame)
    if selection == "all":
        return frame
    raise ValueError(f"Unsupported dispersion selection: {selection}")


def _finalize_figure(fig, output_file, show, *, layout=True, layout_kwargs=None):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if layout:
        fig.tight_layout(**(layout_kwargs or {}))
    _save_figure(output_file, fig)
    log.info("Saved plot %s", output_file)
    if show:
        plt.show()
    else:
        plt.close(fig)


# Preserve public type identities for annotations and pickled caller objects.
InvalidPlotData.__module__ = "qc_monitor.plotting"
PlotSeries.__module__ = "qc_monitor.plotting"
