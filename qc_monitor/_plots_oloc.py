"""Explicit OLOC renderers, preserving scientific selection and layout."""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from ._plots_common import (
    _finalize_figure,
    InvalidPlotData,
    _latest_time_rows,
    _renderer,
    _valid_rows,
    log,
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

    _finalize_figure(fig, output_file, show)
