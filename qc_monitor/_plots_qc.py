"""Explicit QC renderers, preserving scientific selection and layout."""
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from ._plots_common import (
    _finalize_figure,
    InvalidPlotData,
    PlotSeries,
    _apply_time_range,
    _latest_time_rows,
    _normalize_order_label,
    _prepare_scalar_series,
    _prepare_xy,
    _renderer,
    _require_columns,
    _series_from_config,
    _style_to_matplotlib,
    _valid_rows,
    log,
    resolve_datapoint_query,
)


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

    _finalize_figure(fig, output_file, show)


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

    _finalize_figure(fig, output_file, show)


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

    _finalize_figure(fig, output_file, show)


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

    _finalize_figure(fig, output_file, show)
