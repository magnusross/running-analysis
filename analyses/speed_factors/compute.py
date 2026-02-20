"""Speed-factor computation logic."""

import pandas as pd

from parkrun.utils import format_time


def compute_stats(
    df: pd.DataFrame,
    percentile: float,
    min_n: int,
    method: str = "percentile",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute per-course summary stats for each gender.

    Args:
        method: how to derive the reference time used for speed factors.
            "percentile" — Nth percentile finish time (set by `percentile`)
            "fastest"    — single fastest finish time ever recorded

    Returns (men, women) DataFrames with columns:
        n, fastest, median, p_ref, *_fmt variants, factor (added by add_speed_factors)
    """
    def _p_ref(x):
        return x.min() if method == "fastest" else x.quantile(percentile)

    stats = (
        df.groupby(["Event Name", "Gender"])["mins"]
        .agg(
            n="count",
            fastest="min",
            median="median",
            p_ref=_p_ref,
        )
        .reset_index()
        .query("n >= @min_n")
        .assign(
            fastest_fmt=lambda d: d["fastest"].map(format_time),
            p_ref_fmt=lambda d: d["p_ref"].map(format_time),
            median_fmt=lambda d: d["median"].map(format_time),
        )
    )

    men = stats[stats["Gender"] == "Male"].copy()
    women = stats[stats["Gender"] == "Female"].copy()
    return men, women


def add_speed_factors(men: pd.DataFrame, women: pd.DataFrame) -> None:
    """Add a 'factor' column in-place.

    factor = fastest_p_ref / this_course_p_ref
    Fastest course gets 1.0; slower courses get < 1.0.
    """
    for df_g in (men, women):
        ref = df_g["p_ref"].min()
        df_g["factor"] = ref / df_g["p_ref"]


def compute_combined(men: pd.DataFrame, women: pd.DataFrame) -> pd.DataFrame:
    """Average men and women speed factors into one DataFrame per course."""
    both = men[["Event Name", "factor"]].merge(
        women[["Event Name", "factor"]],
        on="Event Name",
        suffixes=("_men", "_women"),
    )
    both["combined"] = (both["factor_men"] + both["factor_women"]) / 2
    return both
