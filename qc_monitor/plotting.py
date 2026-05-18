import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
import matplotlib.pyplot as plt

log = logging.getLogger(__name__)


SeriesStyle = Literal["markers", "line", "line+markers"]


@dataclass
class PlotSeries:
    filters: dict[str, object]
    label: str
    style: SeriesStyle = "line+markers"


def _apply_filters(df: pd.DataFrame, filters: dict[str, object]) -> pd.DataFrame:
    out = df

    for column, value in filters.items():
        if column not in out.columns:
            log.warning("Filter column %s not found in dataframe", column)
            return out.iloc[0:0]

        out = out[out[column] == value]

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
        filters=series_cfg.get("filters", {}),
        label=series_cfg["label"],
        style=series_cfg.get("style", "line+markers"),
    )


def plot_time_series(
    df: pd.DataFrame,
    series: list[PlotSeries],
    title: str,
    output_file: Path,
    time_range: str = "all",
    x_column: str = "obs_date_utc",
    y_column: str = "qc_value",
    y_label: str | None = None,
    show: bool = False,
):
    """
    Plot one or more time series on the same figure.

    The input dataframe is expected to use upstream column names.
    """
    if df.empty:
        log.warning("Cannot create plot %s: empty dataframe", title)
        return

    plt.figure(figsize=(9, 4.8))

    plotted_anything = False

    for s in series:
        df_s = _apply_filters(df, s.filters)

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

        df_s = df_s.copy()
        df_s["_x"] = pd.to_datetime(df_s[x_column], errors="coerce")
        df_s["_y"] = pd.to_numeric(df_s[y_column], errors="coerce")
        df_s = df_s.dropna(subset=["_x", "_y"]).sort_values("_x")

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


def plot_time_series_from_config(
    df: pd.DataFrame,
    plot_cfg: dict,
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
    output_dir: Path,
    show: bool = False,
):
    plot_type = plot_cfg.get("type")

    if plot_type == "time_series":
        return plot_time_series_from_config(
            df=df,
            plot_cfg=plot_cfg,
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

    figures = plots_cfg.get("figures", [])

    if not figures:
        log.info("No plot figures configured")
        return

    for fig_cfg in figures:
        plot_from_config(
            df=df,
            plot_cfg=fig_cfg,
            output_dir=output_dir,
            show=show,
        )