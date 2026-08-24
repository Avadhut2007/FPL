"""
Turns raw features into a single 'predicted_points' score per player.
This is a transparent weighted-heuristic model (not a black box) so you can
see exactly why a player is rated highly and tune the weights in config.py.
"""
import pandas as pd

import config


def _normalize(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi == lo:
        return series.apply(lambda x: 0.5)
    return (series - lo) / (hi - lo)


def compute_predicted_points(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["form_norm"] = _normalize(df["form"])
    df["ppg_norm"] = _normalize(df["points_per_game"])
    df["ict_norm"] = _normalize(df["ict_index"])
    df["minutes_reliability"] = (df["avg_minutes_per_gw"] / config.MIN_RELIABLE_MINUTES).clip(upper=1.0)

    w = config.WEIGHTS
    df["predicted_points"] = (
        w["form"] * df["form_norm"]
        + w["points_per_game"] * df["ppg_norm"]
        + w["fixture_score"] * df["fixture_score"]
        + w["ict_index"] * df["ict_norm"]
        + w["minutes_reliability"] * df["minutes_reliability"]
    ) * 10

    df["value"] = (df["predicted_points"] / df["price"]).round(3)

    return df.sort_values("predicted_points", ascending=False).reset_index(drop=True)
