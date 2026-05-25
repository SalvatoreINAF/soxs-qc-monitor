import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import pandas as pd

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


def _apply_filters(df: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    out = df

    for column, value in filters.items():
        if column not in out.columns:
            log.warning("Filter column %s not found in dataframe", column)
            return out.iloc[0:0]

        out = out[out[column] == value]

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

    if time_column not in df.columns:
        log.warning("Time column %s not found", time_column)
        return df.iloc[0:0]

    times = pd.to_datetime(df[time_column], errors="coerce")
    max_time = times.max()

    if pd.isna(max_time):
        log.warning("Cannot apply time range: no valid timestamps found")
        return df.iloc[0:0]

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
    out = df.copy()
    out["_x"] = pd.to_datetime(out[x_column], errors="coerce")
    out["_y"] = pd.to_numeric(out[y_column], errors="coerce")
    return out.dropna(subset=["_x", "_y"]).sort_values("_x")


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

    plt.figure(figsize=(9, 4.8))

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

        if x_column not in df_s.columns:
            log.warning("X column %s not found for series %s", x_column, s.label)
            continue

        if y_column not in df_s.columns:
            log.warning("Y column %s not found for series %s", y_column, s.label)
            continue

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
        plt.close()
        log.warning("Skipping plot %s: no valid series", title)
        return

    plt.title(title)
    plt.xlabel("UTC date")
    plt.ylabel(y_label if y_label else y_column)
    plt.grid(True)
    plt.legend()

    output_file.parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    plt.savefig(output_file)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close()


def _prepare_scalar_series(
    df: pd.DataFrame,
    value_column: str,
    join_column: str,
) -> pd.DataFrame:
    out = df.copy()

    if join_column not in out.columns:
        log.warning("Join column %s not found", join_column)
        return out.iloc[0:0]

    if value_column not in out.columns:
        log.warning("Value column %s not found", value_column)
        return out.iloc[0:0]

    out["_value"] = pd.to_numeric(out[value_column], errors="coerce")
    out = out.dropna(subset=[join_column, "_value"])

    # If multiple rows exist for the same observing day, average them.
    # This keeps xy plots well-defined without requiring identical sampling.
    out = (
        out.groupby(join_column, as_index=False)["_value"]
        .mean()
    )

    return out


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

    plt.figure(figsize=(6.5, 5.5))
    plt.scatter(merged["_x"], merged["_y"])

    plt.title(title)
    plt.xlabel(x_cfg.get("label", x_cfg["datapoint_query"]))
    plt.ylabel(y_cfg.get("label", y_cfg["datapoint_query"]))
    plt.grid(True)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    plt.savefig(output_file)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close()


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

    values = pd.to_numeric(df_s[value_column], errors="coerce").dropna()

    if values.empty:
        log.warning("No valid numeric values for histogram %s", title)
        return

    bins = int(plot_cfg.get("bins", 30))

    plt.figure(figsize=(7, 5))
    plt.hist(values, bins=bins)

    plt.title(title)
    plt.xlabel(plot_cfg.get("x_label", value_column))
    plt.ylabel(plot_cfg.get("y_label", "Count"))
    plt.grid(True)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    plt.savefig(output_file)

    log.info("Saved plot %s", output_file)

    if show:
        plt.show()
    else:
        plt.close()


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
        log.warning("Plot %s has no series configured", plot_cfg.get("name", "<unnamed>"))
        return

    filename = plot_cfg["filename"]
    output_file = output_dir / filename

    plot_time_series(
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

    raise ValueError(f"Unsupported plot type: {plot_type}")


def generate_plots_from_config(
    df: pd.DataFrame,
    plots_cfg: dict,
):
    output_dir = Path(plots_cfg.get("output_dir", "plots"))
    show = bool(plots_cfg.get("show", False))

    datapoint_queries = plots_cfg.get("datapoint_queries", {})
    figures = plots_cfg.get("figures", [])

    if not datapoint_queries:
        log.warning("No datapoint queries configured")

    if not figures:
        log.info("No plot figures configured")
        return

    for fig_cfg in figures:
        plot_from_config(
            df=df,
            plot_cfg=fig_cfg,
            datapoint_queries=datapoint_queries,
            output_dir=output_dir,
            show=show,
        )