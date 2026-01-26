import pandas as pd
import logging

def filter_complete_recipes(
    df_all: pd.DataFrame,
    cfg: dict,
    arm: str,
    log: logging.Logger,
) -> pd.DataFrame:
    """
    Keep only (obs_date, recipe) groups that contain all required metrics
    for the given arm, as defined in cfg["recipes"].

    If a recipe/arm is not defined in config, we keep the data but log a warning.
    """
    if df_all.empty:
        return df_all

    recipes_cfg = cfg.get("recipes", {})
    kept_frames = []

    for (obs_date, recipe), df_grp in df_all.groupby(["obs_date", "recipe"], sort=False):
        recipe_cfg = recipes_cfg.get(recipe, {})
        arm_cfg = recipe_cfg.get(arm)

        if arm_cfg is None:
            log.warning(
                "No recipe definition for %s (%s). Keeping data without completeness check.",
                recipe,
                arm,
            )
            kept_frames.append(df_grp)
            continue

        required = set(arm_cfg.get("required_metrics", []))
        present = set(df_grp["metric"].unique())
        missing = required - present

        if missing:
            log.warning(
                "Skipping %s / %s (%s): incomplete recipe, missing: %s",
                obs_date,
                recipe,
                arm,
                ", ".join(sorted(missing)),
            )
            continue

        # Keep only the required metrics (optional, but usually what you want)
        kept_frames.append(df_grp[df_grp["metric"].isin(required)])

    if not kept_frames:
        return pd.DataFrame(columns=df_all.columns)

    return pd.concat(kept_frames, ignore_index=True)

def filter_complete_recipes_by_arm(
    df_all: pd.DataFrame,
    cfg: dict,
    log: logging.Logger,
) -> pd.DataFrame:
    """
    Apply recipe completeness rules separately for each arm (VIS/NIR).

    Parameters
    ----------
    df_all : pd.DataFrame
        Raw extracted QC metrics (may contain multiple arms).
    cfg : dict
        Full configuration dictionary.
    log : logging.Logger

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame containing only metrics belonging to
        complete recipes, separated by arm.
    """
    if df_all.empty:
        return df_all

    validated_frames = []

    for arm, df_arm in df_all.groupby("arm"):
        log.info(
            "Checking recipe completeness for arm %s (%d metrics)",
            str(arm),
            len(df_arm),
        )

        df_complete = filter_complete_recipes(
            df_arm,
            cfg=cfg,
            arm=str(arm),
            log=log,
        )

        if not df_complete.empty:
            validated_frames.append(df_complete)

    if not validated_frames:
        return pd.DataFrame(columns=df_all.columns)

    return pd.concat(validated_frames, ignore_index=True)
