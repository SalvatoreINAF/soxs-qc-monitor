"""Explicit DETLIN renderers, preserving scientific selection and layout."""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from ._plots_common import (
    _finalize_figure,
    _renderer,
    _valid_rows,
    log,
)


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

    _finalize_figure(fig, output_file, show, layout=False)
