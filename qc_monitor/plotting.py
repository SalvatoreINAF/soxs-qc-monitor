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

log = logging.getLogger(__name__)


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


def _evaluate_order_xy_polynomial(
    order_values: np.ndarray,
    axis_b_values: np.ndarray,
    coeff: list[float],
    order_deg: int,
    axis_b_deg: int,
) -> np.ndarray:
    out = np.zeros_like(axis_b_values, dtype=float)
    n_coeff = 0

    for i in range(order_deg + 1):
        for j in range(axis_b_deg + 1):
            out += coeff[n_coeff] * (order_values ** i) * (axis_b_values ** j)
            n_coeff += 1

    return out


def _extract_poly_coefficients(
    row: pd.Series,
    prefix: str,
    order_deg: int,
    axis_b_deg: int,
    separator: str = "_",
) -> list[float]:
    coeff = []

    for i in range(order_deg + 1):
        for j in range(axis_b_deg + 1):
            key = f"{prefix}{separator}{i}{j}"
            value = float(row[key])
            if not np.isfinite(value):
                raise InvalidPlotData(f'Invalid polynomial coefficient: {key}')
            coeff.append(value)

    return coeff


def _select_latest_oloc(
    df: pd.DataFrame,
    arm: str,
    recipe: str | None = None,
    slit: str | None = None,
) -> pd.DataFrame:
    df_s = df[df["eso seq arm"] == arm].copy()

    if recipe is not None:
        df_s = df_s[df_s["soxspipe_recipe"] == recipe].copy()

    if slit is not None:
        df_s = df_s[df_s["slit"] == slit].copy()

    if df_s.empty:
        return df_s

    return _latest_time_rows(df_s)


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


@_renderer
def plot_time_series(
    df: pd.DataFrame,
    series: list[PlotSeries],
    datapoint_queries: dict,
    title: str,
    output_file: Path,
    time_range: str = "all",
    x_column: str = "obs_date_utc",
    y_column: str = "qc_value",
    y_label: str | None = None,
    show: bool = False,
):
    if df.empty:
        log.warning("Cannot create plot %s: empty dataframe", title)
        return

    fig = plt.figure(figsize=(9, 4.8))

    plotted_anything = False

    for s in series:
        df_s = resolve_datapoint_query(
            df=df,
            query_name=s.query_name,
            datapoint_queries=datapoint_queries,
        )

        if df_s.empty:
            log.warning("No data found for series %s", s.label)
            continue

        _require_columns(df_s, [x_column, y_column])

        df_s = _apply_time_range(
            df_s,
            time_column=x_column,
            time_range=time_range,
        )

        if df_s.empty:
            log.warning("No data left after time filtering for series %s", s.label)
            continue

        df_s = _prepare_xy(
            df_s,
            x_column=x_column,
            y_column=y_column,
        )

        if df_s.empty:
            log.warning("No valid numeric data for series %s", s.label)
            continue

        style_kwargs = _style_to_matplotlib(s.style)

        plt.plot(
            df_s["_x"],
            df_s["_y"],
            label=s.label,
            **style_kwargs,
        )

        plotted_anything = True

    if not plotted_anything:
        plt.close(fig)
        log.warning("Skipping plot %s: no valid series", title)
        return

    plt.title(title)
    plt.xlabel("UTC date")
    plt.ylabel(y_label if y_label else y_column)
    plt.grid(True)
    plt.legend()

    output_file.parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


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


@_renderer
def plot_xy_scatter_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    datapoint_queries: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    time_range = plot_cfg.get("time_range", "all")
    time_column = plot_cfg.get("time_column", "obs_date_utc")
    value_column = plot_cfg.get("value_column", "qc_value")
    join_column = plot_cfg.get("join_on", "night start date")

    x_cfg = plot_cfg["x"]
    y_cfg = plot_cfg["y"]

    df_x = resolve_datapoint_query(
        df=df,
        query_name=x_cfg["datapoint_query"],
        datapoint_queries=datapoint_queries,
    )
    df_y = resolve_datapoint_query(
        df=df,
        query_name=y_cfg["datapoint_query"],
        datapoint_queries=datapoint_queries,
    )

    df_x = _apply_time_range(df_x, time_column=time_column, time_range=time_range)
    df_y = _apply_time_range(df_y, time_column=time_column, time_range=time_range)

    sx = _prepare_scalar_series(
        df_x,
        value_column=value_column,
        join_column=join_column,
    ).rename(columns={"_value": "_x"})

    sy = _prepare_scalar_series(
        df_y,
        value_column=value_column,
        join_column=join_column,
    ).rename(columns={"_value": "_y"})

    merged = pd.merge(sx, sy, on=join_column, how="inner")

    log.info(
        "XY plot %s matched %d common observing days",
        plot_cfg.get("name", title),
        len(merged),
    )

    if len(merged) < 2:
        log.warning("Skipping XY plot %s: fewer than 2 common points", title)
        return

    fig = plt.figure(figsize=(6.5, 5.5))
    plt.scatter(merged["_x"], merged["_y"])

    plt.title(title)
    plt.xlabel(x_cfg.get("label", x_cfg["datapoint_query"]))
    plt.ylabel(y_cfg.get("label", y_cfg["datapoint_query"]))
    plt.grid(True)
    plt.axis("equal")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


@_renderer
def plot_histogram_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    datapoint_queries: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    query_name = plot_cfg["datapoint_query"]
    time_range = plot_cfg.get("time_range", "all")
    time_column = plot_cfg.get("time_column", "obs_date_utc")
    value_column = plot_cfg.get("value_column", "qc_value")

    df_s = resolve_datapoint_query(
        df=df,
        query_name=query_name,
        datapoint_queries=datapoint_queries,
    )

    df_s = _apply_time_range(
        df_s,
        time_column=time_column,
        time_range=time_range,
    )

    if df_s.empty:
        log.warning("No data found for histogram %s", title)
        return

    values = _valid_rows(df_s, [value_column], numeric=[value_column],
                         context=value_column)[value_column]

    bins = int(plot_cfg.get("bins", 30))

    fig = plt.figure(figsize=(7, 5))
    plt.hist(values, bins=bins)

    plt.title(title)
    plt.xlabel(plot_cfg.get("x_label", value_column))
    plt.ylabel(plot_cfg.get("y_label", "Count"))
    plt.grid(True)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


@_renderer
def plot_time_series_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    datapoint_queries: dict,
    output_dir: Path,
    show: bool = False,
):
    series = [
        _series_from_config(s)
        for s in plot_cfg.get("series", [])
    ]

    if not series:
        raise InvalidPlotData('No series configured')

    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    return plot_time_series(
        df=df,
        series=series,
        datapoint_queries=datapoint_queries,
        title=plot_cfg.get("title", plot_cfg.get("name", "")),
        output_file=output_file,
        time_range=plot_cfg.get("time_range", "all"),
        x_column=plot_cfg.get("x_column", "obs_date_utc"),
        y_column=plot_cfg.get("y_column", "qc_value"),
        y_label=plot_cfg.get("y_label"),
        show=show,
    )


@_renderer
def plot_dispersion_resolution_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    aspect = plot_cfg.get("aspect", None)
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    arm = plot_cfg["arm"]
    selection = plot_cfg.get("selection", "latest")

    df_s = df[df["eso seq arm"] == arm].copy()

    if df_s.empty:
        log.warning("No dispersion-solution data found for arm %s", arm)
        return

    if selection == "latest":
        df_s = _latest_time_rows(df_s)

    elif selection == "all":
        pass

    else:
        raise ValueError(f"Unsupported dispersion selection: {selection}")

    if df_s.empty:
        log.warning("No dispersion-solution data left after time filtering for %s", title)
        return

    df_s = _valid_rows(df_s, ['wavelength', 'R_pin', 'order'],
                       numeric=['wavelength', 'R_pin'], series=['order'], context='wavelength/resolution')

    if df_s.empty:
        log.warning("No valid wavelength/R_pin data for %s", title)
        return

    fig, ax = plt.subplots(figsize=(9, 5))

    for order, group in df_s.groupby("order"):
        group = group.sort_values("wavelength")

        ax.scatter(
            group["wavelength"],
            group["R_pin"],
            alpha=0.5,
            s=10,
            label=f"Order {order}",
        )

        mean_wavelength = group["wavelength"].mean()
        mean_resolution = group["R_pin"].mean()
        std_resolution = group["R_pin"].std()

        ax.errorbar(
            mean_wavelength,
            mean_resolution,
            yerr=std_resolution,
            fmt="o",
            color="black",
            alpha=0.7,
            markersize=4,
        )

    ax.set_title(title)
    ax.set_xlabel("Wavelength [nm]")
    ax.set_ylabel("Resolution R")
    ax.grid(True)
    if aspect is not None:
        ax.set_aspect(float(aspect), adjustable="box")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    fig.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


@_renderer
def plot_dispersion_resolution_timeseries_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    arm = plot_cfg["arm"]
    min_n_points = int(plot_cfg.get("min_n_points", 2))

    df_s = df[df["eso seq arm"] == arm].copy()

    if df_s.empty:
        log.warning("No dispersion resolution stats found for arm %s", arm)
        return

    df_s = _valid_rows(df_s, ['obs_date_utc', 'order', 'mean_R_pin', 'n_points'],
                       numeric=['mean_R_pin', 'n_points'], dates=['obs_date_utc'],
                       series=['order'], context='resolution statistics')
    df_s['std_R_pin'] = pd.to_numeric(df_s['std_R_pin'], errors='coerce')
    df_s = df_s[df_s["n_points"] >= min_n_points]

    if df_s.empty:
        log.warning("No valid resolution stats left for plot %s", title)
        return

    fig, ax = plt.subplots(figsize=tuple(plot_cfg.get("figsize", [12, 5])))

    for order, group in df_s.groupby("order"):
        group = group.sort_values("obs_date_utc")
        order_label = _normalize_order_label(order)

        ax.errorbar(
            group["obs_date_utc"],
            group["mean_R_pin"],
            yerr=group["std_R_pin"],
            marker="o",
            linestyle="-",
            capsize=2,
            label=f"Order {order_label}",
        )

    ax.set_title(title)
    ax.set_xlabel(plot_cfg.get("x_label", "Date"))
    ax.set_ylabel(plot_cfg.get("y_label", "Mean resolution R"))
    ax.grid(True)

    ax.legend(
        fontsize=plot_cfg.get("legend_fontsize", 7),
        ncol=plot_cfg.get("legend_ncol", 4),
        loc=plot_cfg.get("legend_loc", "best"),
    )

    fig.autofmt_xdate()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


@_renderer
def plot_dispersion_residual_xy_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    arm = plot_cfg["arm"]
    selection = plot_cfg.get("selection", "latest")

    df_s = df[df["eso seq arm"] == arm].copy()

    if df_s.empty:
        log.warning("No dispersion-solution data found for arm %s", arm)
        return

    if selection == "latest":
        df_s = _latest_time_rows(df_s)

    elif selection == "all":
        pass
    else:
        raise ValueError(f"Unsupported dispersion selection: {selection}")

    df_s = _valid_rows(df_s, ['residuals_x', 'residuals_y'],
                       numeric=['residuals_x', 'residuals_y'], context='residuals')

    if df_s.empty:
        log.warning("No valid residual_x/residual_y data for %s", title)
        return

    fig, ax = plt.subplots(figsize=(6, 6))

    ax.scatter(
        df_s["residuals_x"],
        df_s["residuals_y"],
        alpha=0.85,
        s=10,
        edgecolors="none",
    )

    ax.axhline(0, linestyle="--", linewidth=1)
    ax.axvline(0, linestyle="--", linewidth=1)

    ax.set_title(title)
    ax.set_xlabel("Residual X [pixels]")
    ax.set_ylabel("Residual Y [pixels]")
    xmin = min(ax.get_xlim()[0], ax.get_ylim()[0])
    xmax = max(ax.get_xlim()[1], ax.get_ylim()[1])
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(xmin, xmax)
    ax.grid(True)
    ax.set_aspect("equal", adjustable="box")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)

    
@_renderer
def plot_dispersion_residual_histogram_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    arm = plot_cfg["arm"]
    selection = plot_cfg.get("selection", "latest")
    bins = int(plot_cfg.get("bins", 40))

    df_s = df[df["eso seq arm"] == arm].copy()

    if df_s.empty:
        log.warning("No dispersion-solution data found for arm %s", arm)
        return

    if selection == "latest":
        df_s = _latest_time_rows(df_s)

    elif selection == "all":
        pass
    else:
        raise ValueError(f"Unsupported dispersion selection: {selection}")

    values = _valid_rows(df_s, ['residuals_xy'], numeric=['residuals_xy'],
                         context='residuals_xy')['residuals_xy']

    figsize = tuple(plot_cfg.get("figsize", [7, 5]))
    fig, ax = plt.subplots(figsize=figsize)

    ax.hist(values, bins=bins)

    ax.set_title(title)
    ax.set_xlabel("Residual XY [pixels]")
    ax.set_ylabel("Count")
    ax.grid(True)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


@_renderer
def plot_latest_by_order_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    datapoint_queries: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    query_name = plot_cfg["datapoint_query"]

    df_s = resolve_datapoint_query(
        df=df,
        query_name=query_name,
        datapoint_queries=datapoint_queries,
    )

    if df_s.empty:
        log.warning("No data found for plot %s", title)
        return

    df_s = _latest_time_rows(df_s)
    df_s = _valid_rows(df_s, ['qc_order', 'qc_value'], numeric=['qc_value'],
                       context='order values')

    df_s["qc_order"] = df_s["qc_order"].apply(_normalize_order_label)

    # qc_order is categorical: VIS = u/g/r/i, NIR = 10..24
    df_s["qc_order"] = df_s["qc_order"].astype(str)

    order_sequence = plot_cfg.get("order_sequence")

    if order_sequence:
        order_sequence = [str(o) for o in order_sequence]

        df_s["qc_order"] = pd.Categorical(
            df_s["qc_order"],
            categories=order_sequence,
            ordered=True,
        )

        df_s = df_s.dropna(subset=["qc_order"]).sort_values("qc_order")
    else:
        df_s = df_s.sort_values("qc_order")
    if df_s.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    x_labels = df_s["qc_order"].astype(str).tolist()
    y_values = df_s["qc_value"].tolist()

    ax.bar(
        x_labels,
        y_values,
    )

    ax.set_title(title)
    ax.set_xlabel(plot_cfg.get("x_label", "Order"))
    ax.set_ylabel(plot_cfg.get("y_label", "Value"))
    ax.grid(True)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


def select_detector_linearity_sequences(df, selection):
    """Select one complete acquisition, never combine fits from a calendar day."""
    if 'fit_state' in df:
        df = df[df['fit_state'] == 'available'].copy()
    if selection == 'all' or df.empty:
        return df
    if selection != 'latest':
        raise ValueError(f'Unsupported detector-linearity selection: {selection}')
    sequences = df[['sequence_id', 'tpl_start']].drop_duplicates().copy()
    sequences['_time'] = pd.to_datetime(sequences['tpl_start'], utc=True, errors='coerce')
    sequences = _valid_rows(sequences, ['_time'], context='sequence timestamps')
    sequences = sequences.sort_values(['_time', 'sequence_id'])
    return df[df['sequence_id'] == sequences['sequence_id'].iloc[-1]].copy()


@_renderer
def plot_detector_linearity_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    arm = plot_cfg.get("arm", "VIS")
    mode_order = plot_cfg.get("mode_order", ["SHG", "FLG", "SLG", "FHG"])
    selection = plot_cfg.get("selection", "latest")
    figsize = tuple(plot_cfg.get("figsize", [11, 8]))

    if df.empty:
        log.warning("No detector-linearity data available for plot %s", title)
        return

    df_s = df[df["eso seq arm"] == arm].copy()

    if df_s.empty:
        log.warning("No detector-linearity data found for arm %s", arm)
        return

    df_s = select_detector_linearity_sequences(df_s, selection)

    numeric_columns = [
        "exptime",
        "signal",
        "fit_signal",
        "fit_used",
        "saturation_limit",
    ]

    for column in numeric_columns:
        df_s[column] = pd.to_numeric(df_s[column], errors="coerce")

    df_s = _valid_rows(df_s, ['exptime', 'signal', 'detector_mode', 'sequence_id'],
                       numeric=['exptime', 'signal'], series=['detector_mode', 'sequence_id'],
                       context='detector measurements')

    if df_s.empty:
        log.warning("No valid detector-linearity data left for plot %s", title)
        return

    if len(mode_order) == 1:
        fig, axes = plt.subplots(1, 1, figsize=figsize, sharey=True)
        axes = np.array([axes])
    else:
        fig, axes = plt.subplots(2, 2, figsize=figsize, sharey=True)
        axes = axes.ravel()

    for ax, mode in zip(axes, mode_order):
        group = df_s[df_s["detector_mode"] == mode].copy()

        if group.empty:
            ax.set_title(f"{mode} - no data")
            ax.grid(True)
            continue

        for sequence_id, group in group.groupby('sequence_id', sort=True):
            prefix = (f"{group['tpl_start'].iloc[0]} {group['tpl_id'].iloc[0]} — "
                      if selection == 'all' else '')
            group = group.sort_values("exptime")
            used = group["fit_used"].fillna(0).astype(bool)

            ax.plot(
                group["exptime"],
                group["signal"],
                marker="o",
                linestyle="-",
                label=prefix + "Measured",
            )

            if used.any():
                ax.scatter(
                    group.loc[used, "exptime"],
                    group.loc[used, "signal"],
                    s=28,
                    label=prefix + "Fit points",
                )

            if (~used).any():
                ax.scatter(
                    group.loc[~used, "exptime"],
                    group.loc[~used, "signal"],
                    marker="x",
                    s=45,
                    label=prefix + "Excluded",
                )

            fit_group = group.dropna(subset=["fit_signal"])

            if not fit_group.empty and fit_group["fit_signal"].abs().sum() > 0:
                ax.plot(
                    fit_group["exptime"],
                    fit_group["fit_signal"],
                    linestyle="--",
                    label=prefix + "Linear fit",
                )

            saturation_limit = group["saturation_limit"].dropna()
            if not saturation_limit.empty:
                ax.axhline(
                    saturation_limit.iloc[0],
                    linestyle=":",
                    linewidth=1,
                    label=prefix + "Fit threshold",
                )

        ax.set_title(mode)
        ax.set_xlabel(plot_cfg.get("x_label", "Exposure time [s]"))
        ax.grid(True)

    axes[0].set_ylabel(plot_cfg.get("y_label", "Signal [ADU]"))
    if len(axes) > 2:
        axes[2].set_ylabel(plot_cfg.get("y_label", "Signal [ADU]"))

    handles, labels = axes[0].get_legend_handles_labels()
    legend = None
    if handles:
        legend = fig.legend(
            handles,
            labels,
            loc=plot_cfg.get("legend_loc", "lower center"),
            ncol=plot_cfg.get("legend_ncol", 4),
            fontsize=plot_cfg.get('legend_fontsize', 10),
            bbox_to_anchor=(0, 0, 1, .94),
        )

    fig.suptitle(title, y=0.98)
    bottom, top = .06, .95
    if legend is not None:
        fig.canvas.draw()
        bounds = legend.get_window_extent().transformed(fig.transFigure.inverted())
        location = plot_cfg.get('legend_loc', 'lower center')
        if location.startswith('lower'):
            bottom = max(bottom, bounds.y1 + .025)
        elif location.startswith('upper'):
            top = min(top, bounds.y0 - .025)
    fig.tight_layout(rect=[0, bottom, 1, top])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


def plot_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
    datapoint_queries: dict,
    output_dir: Path,
    show: bool = False,
):
    plot_type = plot_cfg.get("type")

    if plot_type == "time_series":
        return plot_time_series_from_config(
            df=df,
            plot_cfg=plot_cfg,
            datapoint_queries=datapoint_queries,
            output_dir=output_dir,
            show=show,
        )

    if plot_type == "xy_scatter":
        return plot_xy_scatter_from_config(
            df=df,
            plot_cfg=plot_cfg,
            datapoint_queries=datapoint_queries,
            output_dir=output_dir,
            show=show,
        )

    if plot_type == "histogram":
        return plot_histogram_from_config(
            df=df,
            plot_cfg=plot_cfg,
            datapoint_queries=datapoint_queries,
            output_dir=output_dir,
            show=show,
        )
    
    if plot_type == "dispersion_resolution":
        return plot_dispersion_resolution_from_config(
            df=df,
            plot_cfg=plot_cfg,
            output_dir=output_dir,
            show=show,
         )
    
    if plot_type == "dispersion_resolution_timeseries":
        return plot_dispersion_resolution_timeseries_from_config(
            df=df,
            plot_cfg=plot_cfg,
            output_dir=output_dir,
            show=show,
        )

    if plot_type == "dispersion_residual_xy":        
        return plot_dispersion_residual_xy_from_config(
            df=df,
            plot_cfg=plot_cfg,
            output_dir=output_dir,
            show=show,
        )

    if plot_type == "dispersion_residual_histogram":
        return plot_dispersion_residual_histogram_from_config(
            df=df,
            plot_cfg=plot_cfg,
            output_dir=output_dir,
            show=show,
        )

    if plot_type == "latest_by_order_bar":
        return plot_latest_by_order_from_config(
            df=df,
            plot_cfg=plot_cfg,
            datapoint_queries=datapoint_queries,
            output_dir=output_dir,
            show=show,
        )

    if plot_type == "detector_linearity":
        return plot_detector_linearity_from_config(
            df=df,
            plot_cfg=plot_cfg,
            output_dir=output_dir,
            show=show,
        )

    raise ValueError(f"Unsupported plot type: {plot_type}")


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


@_renderer
def plot_order_location_fit_from_config(
    df_models: pd.DataFrame,
    df_meta: pd.DataFrame,
    plot_cfg: dict,
    output_dir: Path,
    show: bool = False,
):
    title = plot_cfg.get("title", plot_cfg.get("name", ""))
    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    arm = plot_cfg["arm"]
    recipe = plot_cfg.get("recipe")
    slit = plot_cfg.get("slit")
    axis_b_step = int(plot_cfg.get("axis_b_step", 3))

    df_s = _select_latest_oloc(
        df_models,
        arm=arm,
        recipe=recipe,
        slit=slit,
    )

    if df_s.empty:
        log.warning("No order-location data found for plot %s", title)
        return

    # Each row is one OLOC model file.
    row = df_s.iloc[0]

    source_file = row["source_file"]

    identity = 'filepath' if 'filepath' in df_meta and pd.notna(row.get('filepath')) else 'source_file'
    df_meta_s = df_meta[df_meta[identity] == row[identity]].copy()

    if df_meta_s.empty:
        log.warning(
            "No order-location meta rows found for %s",
            source_file,
        )
        raise InvalidPlotData(f'No order-location metadata for {source_file}')

    def _get_first_valid(row: pd.Series, names: list[str]) -> float:
        for name in names:
            if name not in row.index:
                continue

            value = row[name]

            if pd.isna(value):
                continue

            number = float(value)
            if not np.isfinite(number) or number < 0 or not number.is_integer():
                raise InvalidPlotData(f'Invalid polynomial degree: {name}')
            return number

        raise ValueError(f"None of these columns has a valid value: {names}")

    try:
        order_deg = int(_get_first_valid(row, ["degorder_cent"]))
        axis_b_deg = int(_get_first_valid(row, ["degy_cent", "degx_cent"]))

        edgelow_order_deg = int(_get_first_valid(row, ["degorder_edgelow"]))
        edgelow_axis_b_deg = int(_get_first_valid(row, ["degy_edgelow", "degx_edgelow"]))

        edgeup_order_deg = int(_get_first_valid(row, ["degorder_edgeup"]))
        edgeup_axis_b_deg = int(_get_first_valid(row, ["degy_edgeup", "degx_edgeup"]))
    except ValueError as exc:
        log.warning(
            "Skipping order-location plot %s: invalid polynomial degree in %s: %s",
            title,
            row.get("source_file", "<unknown>"),
            exc,
        )
        raise InvalidPlotData(f'Invalid polynomial degree: {exc}') from exc

    cent_coeff = _extract_poly_coefficients(
        row=row,
        prefix="cent",
        order_deg=order_deg,
        axis_b_deg=axis_b_deg,
        separator="_",
    )

    edgelow_coeff = _extract_poly_coefficients(
        row=row,
        prefix="edgelow_c",
        order_deg=edgelow_order_deg,
        axis_b_deg=edgelow_axis_b_deg,
        separator="",
    )

    edgeup_coeff = _extract_poly_coefficients(
        row=row,
        prefix="edgeup_c",
        order_deg=edgeup_order_deg,
        axis_b_deg=edgeup_axis_b_deg,
        separator="",
    )

    degrees = [order_deg, axis_b_deg, edgelow_order_deg, edgelow_axis_b_deg,
               edgeup_order_deg, edgeup_axis_b_deg]
    if any(degree < 0 for degree in degrees):
        raise InvalidPlotData('Polynomial degrees must be nonnegative')

    if pd.notna(row.get("degy_cent")):
        axis_a = "x"
        axis_b_name = "y"
    else:
        axis_a = "y"
        axis_b_name = "x"

    df_meta_s = _valid_rows(df_meta_s, ['order', f'{axis_b_name}min', f'{axis_b_name}max'],
                            numeric=['order', f'{axis_b_name}min', f'{axis_b_name}max'],
                            series=['order'], context='order-location geometry')
    if (df_meta_s[f'{axis_b_name}max'] <= df_meta_s[f'{axis_b_name}min']).any():
        raise InvalidPlotData('Invalid order-location geometry bounds')
    if axis_b_step <= 0:
        raise InvalidPlotData('axis_b_step must be positive')
    figsize = tuple(plot_cfg.get("figsize", [8, 8]))
    fig, ax = plt.subplots(figsize=figsize)

    for _, meta_row in df_meta_s.sort_values("order").iterrows():
        order = float(meta_row["order"])

        axis_b_min = float(meta_row[f"{axis_b_name}min"])
        axis_b_max = float(meta_row[f"{axis_b_name}max"])

        axis_b = np.arange(
            axis_b_min,
            axis_b_max,
            axis_b_step,
            dtype=float,
        )

        order_values = np.full_like(axis_b, order, dtype=float)

        centre = _evaluate_order_xy_polynomial(
            order_values=order_values,
            axis_b_values=axis_b,
            coeff=cent_coeff,
            order_deg=order_deg,
            axis_b_deg=axis_b_deg,
        )

        edge_low = _evaluate_order_xy_polynomial(
            order_values=order_values,
            axis_b_values=axis_b,
            coeff=edgelow_coeff,
            order_deg=edgelow_order_deg,
            axis_b_deg=edgelow_axis_b_deg,
        )

        edge_up = _evaluate_order_xy_polynomial(
            order_values=order_values,
            axis_b_values=axis_b,
            coeff=edgeup_coeff,
            order_deg=edgeup_order_deg,
            axis_b_deg=edgeup_axis_b_deg,
        )

        ax.plot(axis_b, centre, label=f"Order {order:g}")
        ax.fill_between(axis_b, edge_low, edge_up, alpha=1)

    ax.set_title(title)
    ax.set_xlabel(plot_cfg.get("x_label", "x-axis [px]"))
    ax.set_ylabel(plot_cfg.get("y_label", "y-axis [px]"))
    ax.grid(True)
    legend_fontsize = plot_cfg.get("legend_fontsize", 6)

    if plot_cfg.get("show_legend", True):
        ax.legend(
            fontsize=legend_fontsize,
            ncol=plot_cfg.get("legend_ncol", 3),
            loc=plot_cfg.get("legend_loc", "best"),
        )

    aspect = plot_cfg.get("aspect", "equal")

    if aspect == "equal":
        ax.set_aspect("equal", adjustable="box")
    elif aspect is not None and aspect != "auto":
        ax.set_aspect(float(aspect), adjustable="box")
    
    if plot_cfg.get("invert_yaxis", True):
        ax.invert_yaxis()

    output_file.parent.mkdir(parents=True, exist_ok=True)


    fig.tight_layout()
    _save_figure(output_file, fig)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close(fig)


def generate_order_location_plots_from_config(
    df_models: pd.DataFrame,
    df_meta: pd.DataFrame,
    plots_cfg: dict,
    *, continue_on_error: bool = False,
):
    figures = [config for config in plots_cfg.get('figures', [])
               if config.get('type') == 'order_location_fit']
    return _render_configured(figures, lambda config: plot_order_location_fit_from_config(
        df_models, df_meta, config, Path(plots_cfg.get('output_dir', 'plots')),
        bool(plots_cfg.get('show', False))), continue_on_error)
