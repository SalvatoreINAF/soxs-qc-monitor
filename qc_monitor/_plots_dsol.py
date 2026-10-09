"""Explicit DSOL renderers, preserving scientific selection and layout."""
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from ._plots_common import (
    _finalize_figure,
    _select_dispersion_rows,
    _normalize_order_label,
    _renderer,
    _valid_rows,
    log,
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

    df_s = _select_dispersion_rows(df_s, selection)

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

    _finalize_figure(fig, output_file, show)


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

    _finalize_figure(fig, output_file, show, layout=False)


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

    df_s = _select_dispersion_rows(df_s, selection)

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

    _finalize_figure(fig, output_file, show)


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

    df_s = _select_dispersion_rows(df_s, selection)

    values = _valid_rows(df_s, ['residuals_xy'], numeric=['residuals_xy'],
                         context='residuals_xy')['residuals_xy']

    figsize = tuple(plot_cfg.get("figsize", [7, 5]))
    fig, ax = plt.subplots(figsize=figsize)

    ax.hist(values, bins=bins)

    ax.set_title(title)
    ax.set_xlabel("Residual XY [pixels]")
    ax.set_ylabel("Count")
    ax.grid(True)

    _finalize_figure(fig, output_file, show)
