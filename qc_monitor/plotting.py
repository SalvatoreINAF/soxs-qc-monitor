import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
import logging

log = logging.getLogger(__name__)


def plot_time_series(
    df: pd.DataFrame,
    metric: str,
    arm: str,
    output_dir: Path,
):
    df_m = df[df["metric"] == metric].copy()

    if df_m.empty:
        log.warning("No data to plot for metric %s (%s)", metric, arm)
        return

    # Sort by observing date
    df_m = df_m.sort_values("obs_date")

    x = pd.to_datetime(df_m["obs_date"], format="%Y-%m-%d")
    y = df_m["value"]

    plt.figure(figsize=(8, 4))
    plt.plot(x, y, marker="o", linestyle="-")
    plt.xlabel("Observing date")
    plt.ylabel(df_m["unit"].iloc[0])
    plt.title(f"{metric} ({arm})")
    plt.grid(True)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{metric.replace(' ', '_')}_{arm}.png"

    plt.tight_layout()
    plt.savefig(out_file)
    plt.close()

    log.info("Saved plot %s", out_file)
