import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
            coeff.append(float(row[key]))

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

    times = pd.to_datetime(df_s["obs_date_utc"], errors="coerce")
    latest_time = times.max()

    if pd.isna(latest_time):
        return df_s.iloc[0:0]

    return df_s[times == latest_time].copy()


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
    _save_figure(output_file)

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
    plt.axis("equal")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    plt.tight_layout()
    _save_figure(output_file)

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
    _save_figure(output_file)

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
        times = pd.to_datetime(df_s["obs_date_utc"], errors="coerce")
        latest_time = times.max()

        if pd.isna(latest_time):
            log.warning("Cannot select latest dispersion solution: no valid obs_date_utc")
            return

        df_s = df_s[times == latest_time].copy()

    elif selection == "all":
        pass

    else:
        raise ValueError(f"Unsupported dispersion selection: {selection}")

    if df_s.empty:
        log.warning("No dispersion-solution data left after time filtering for %s", title)
        return

    df_s["wavelength"] = pd.to_numeric(df_s["wavelength"], errors="coerce")
    df_s["R_pin"] = pd.to_numeric(df_s["R_pin"], errors="coerce")
    df_s = df_s.dropna(subset=["wavelength", "R_pin", "order"])

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

    df_s["obs_date_utc"] = pd.to_datetime(df_s["obs_date_utc"], errors="coerce")
    df_s["mean_R_pin"] = pd.to_numeric(df_s["mean_R_pin"], errors="coerce")
    df_s["std_R_pin"] = pd.to_numeric(df_s["std_R_pin"], errors="coerce")
    df_s["n_points"] = pd.to_numeric(df_s["n_points"], errors="coerce")

    df_s = df_s.dropna(subset=["obs_date_utc", "order", "mean_R_pin"])
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
        times = pd.to_datetime(df_s["obs_date_utc"], errors="coerce")
        latest_time = times.max()

        if pd.isna(latest_time):
            log.warning("Cannot select latest dispersion residuals: no valid obs_date_utc")
            return

        df_s = df_s[times == latest_time].copy()

    elif selection == "all":
        pass
    else:
        raise ValueError(f"Unsupported dispersion selection: {selection}")

    df_s["residuals_x"] = pd.to_numeric(df_s["residuals_x"], errors="coerce")
    df_s["residuals_y"] = pd.to_numeric(df_s["residuals_y"], errors="coerce")
    df_s = df_s.dropna(subset=["residuals_x", "residuals_y"])

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
        times = pd.to_datetime(df_s["obs_date_utc"], errors="coerce")
        latest_time = times.max()

        if pd.isna(latest_time):
            log.warning("Cannot select latest dispersion residuals histogram: no valid obs_date_utc")
            return

        df_s = df_s[times == latest_time].copy()

    elif selection == "all":
        pass
    else:
        raise ValueError(f"Unsupported dispersion selection: {selection}")

    values = pd.to_numeric(df_s["residuals_xy"], errors="coerce").dropna()

    if values.empty:
        log.warning("No valid residuals_xy data for %s", title)
        return

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

    times = pd.to_datetime(df_s["obs_date_utc"], errors="coerce")
    latest_time = times.max()

    if pd.isna(latest_time):
        log.warning("Cannot select latest data for %s: no valid obs_date_utc", title)
        return

    df_s = df_s[times == latest_time].copy()

    df_s["qc_value"] = pd.to_numeric(df_s["qc_value"], errors="coerce")
    df_s = df_s.dropna(subset=["qc_order", "qc_value"]).copy()

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

    if selection == "latest":
        times = pd.to_datetime(df_s["obs_date_utc"], errors="coerce")
        latest_time = times.max()

        if pd.isna(latest_time):
            log.warning("Cannot select latest detector-linearity data: no valid obs_date_utc")
            return

        latest_obs_day = df_s.loc[times == latest_time, "obs_day"].iloc[0]
        df_s = df_s[df_s["obs_day"] == latest_obs_day].copy()
    elif selection == "all":
        pass
    else:
        raise ValueError(f"Unsupported detector-linearity selection: {selection}")

    numeric_columns = [
        "exptime",
        "signal",
        "fit_signal",
        "fit_used",
        "saturation_limit",
    ]

    for column in numeric_columns:
        df_s[column] = pd.to_numeric(df_s[column], errors="coerce")

    df_s = df_s.dropna(subset=["exptime", "signal", "detector_mode"])

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

        group = group.sort_values("exptime")
        used = group["fit_used"].fillna(0).astype(bool)

        ax.plot(
            group["exptime"],
            group["signal"],
            marker="o",
            linestyle="-",
            label="Measured",
        )

        if used.any():
            ax.scatter(
                group.loc[used, "exptime"],
                group.loc[used, "signal"],
                s=28,
                label="Fit points",
            )

        if (~used).any():
            ax.scatter(
                group.loc[~used, "exptime"],
                group.loc[~used, "signal"],
                marker="x",
                s=45,
                label="Excluded",
            )

        fit_group = group.dropna(subset=["fit_signal"])

        if not fit_group.empty and fit_group["fit_signal"].abs().sum() > 0:
            ax.plot(
                fit_group["exptime"],
                fit_group["fit_signal"],
                linestyle="--",
                label="Linear fit",
            )

        saturation_limit = group["saturation_limit"].dropna()
        if not saturation_limit.empty:
            ax.axhline(
                saturation_limit.iloc[0],
                linestyle=":",
                linewidth=1,
                label="Fit threshold",
            )

        ax.set_title(mode)
        ax.set_xlabel(plot_cfg.get("x_label", "Exposure time [s]"))
        ax.grid(True)

    axes[0].set_ylabel(plot_cfg.get("y_label", "Signal [ADU]"))
    if len(axes) > 2:
        axes[2].set_ylabel(plot_cfg.get("y_label", "Signal [ADU]"))

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        fig.legend(
            handles,
            labels,
            loc=plot_cfg.get("legend_loc", "lower center"),
            ncol=plot_cfg.get("legend_ncol", 4),
        )

    fig.suptitle(title, y=0.98)
    fig.tight_layout(rect=[0, 0.06, 1, 0.95])

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


def generate_plots_from_config(
    df: pd.DataFrame,
    plots_cfg: dict,
    plot_types: set[str] | None = None,
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
        if plot_types is not None and fig_cfg.get("type") not in plot_types:
            continue

        plot_from_config(
            df=df,
            plot_cfg=fig_cfg,
            datapoint_queries=datapoint_queries,
            output_dir=output_dir,
            show=show,
        )

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

    df_meta_s = df_meta[df_meta["source_file"] == source_file].copy()

    if df_meta_s.empty:
        log.warning(
            "No order-location meta rows found for %s",
            source_file,
        )
        return

    def _get_first_valid(row: pd.Series, names: list[str]) -> float:
        for name in names:
            if name not in row.index:
                continue

            value = row[name]

            if pd.isna(value):
                continue

            return float(value)

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
        return

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

    if pd.notna(row.get("degy_cent")):
        axis_a = "x"
        axis_b_name = "y"
    else:
        axis_a = "y"
        axis_b_name = "x"

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
):
    output_dir = Path(plots_cfg.get("output_dir", "plots"))
    show = bool(plots_cfg.get("show", False))

    figures = plots_cfg.get("figures", [])

    for fig_cfg in figures:
        if fig_cfg.get("type") != "order_location_fit":
            continue

        plot_order_location_fit_from_config(
            df_models=df_models,
            df_meta=df_meta,
            plot_cfg=fig_cfg,
            output_dir=output_dir,
            show=show,
        )
