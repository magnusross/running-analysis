"""
Parkrun Course Speed Factors
=============================
Derives a speed factor for every parkrun course from a reference finish time.
Multiply your time by a course's factor to get the equivalent on the fastest course.

    speed_factor = ref_fastest_course / ref_this_course     (fastest course → 1.00)

Two methods for the reference time (set METHOD below):
    "percentile" — Nth-percentile finish time across all results for the course
    "fastest"    — single fastest time ever recorded at the course

Outputs are saved to results/speed-factors/.

Usage (from repo root):
    python analyses/speed_factors/run.py
"""

import os

import pandas as pd

from parkrun.data import load_data
from compute import add_speed_factors, compute_combined, compute_stats
from plots import plot_factors, plot_mf_sanity

# ── Configuration ──────────────────────────────────────────────────────────────
METHOD = "percentile"  # "percentile" or "fastest"
PERCENTILE = 0.01  # only used when METHOD = "percentile" (e.g. 0.05 for 5th)
MIN_N = 100  # minimum finishers per course/gender to include
OUT_DIR = "results/speed-factors"
DATA_PATH = "Parkrun_2025.parquet"

# Sanity check — equivalent time at the fastest course
SANITY_COURSE = "Hackney Marshes parkrun"
SANITY_TIME = "15:50"
# ──────────────────────────────────────────────────────────────────────────────


def _ref_labels(method: str, percentile: float) -> tuple[str, str]:
    """Return (short_str, display_label) for the reference time method."""
    if method == "fastest":
        return "Fastest", "Fastest"
    pct = round(percentile * 100)
    return f"P{pct}", f"{pct}th Pct"


def save_fastest_tables(
    men: pd.DataFrame,
    women: pd.DataFrame,
    ref_label: str,
    method: str,
    out_dir: str,
    top_n: int = 25,
) -> None:
    """Save top-N courses ranked by absolute fastest time, one CSV per gender."""
    # When method is "fastest", p_ref == fastest so the column would be a duplicate
    cols = {"fastest_fmt": "Fastest"}
    if method == "percentile":
        cols["p_ref_fmt"] = ref_label
    cols.update({"median_fmt": "Median", "n": "Runners"})

    for tag, df_g in [("men", men), ("women", women)]:
        table = (
            df_g.nsmallest(top_n, "fastest")[["Event Name"] + list(cols)]
            .rename(columns=cols)
            .reset_index(drop=True)
        )
        _write_csv(table, out_dir, f"fastest_courses_{tag}.csv")


def save_factor_tables(
    men: pd.DataFrame,
    women: pd.DataFrame,
    ref_label: str,
    method: str,
    out_dir: str,
    top_n: int = 30,
    bottom_n: int = 20,
) -> None:
    """Save fastest/slowest courses ranked by speed factor, one CSV each."""
    cols = {"factor": "Speed Factor"}
    if method == "percentile":
        cols["p_ref_fmt"] = ref_label
    cols.update({"fastest_fmt": "Fastest", "n": "Runners"})

    for tag, df_g in [("men", men), ("women", women)]:
        fastest = df_g.nlargest(top_n, "factor")[["Event Name"] + list(cols)].rename(
            columns=cols
        )
        slowest = df_g.nsmallest(bottom_n, "factor")[
            ["Event Name"] + list(cols)
        ].rename(columns=cols)
        _write_csv(
            fastest.reset_index(drop=True), out_dir, f"speed_factors_fastest_{tag}.csv"
        )
        _write_csv(
            slowest.reset_index(drop=True), out_dir, f"speed_factors_slowest_{tag}.csv"
        )


def save_combined_tables(both: pd.DataFrame, out_dir: str, top_n: int = 30) -> None:
    """Save fastest/slowest combined (M+F average) tables, plus the full ranking."""
    cols = {"combined": "Combined", "factor_men": "Men", "factor_women": "Women"}
    fastest = both.nlargest(top_n, "combined")[["Event Name"] + list(cols)].rename(
        columns=cols
    )
    slowest = both.nsmallest(top_n, "combined")[["Event Name"] + list(cols)].rename(
        columns=cols
    )
    _write_csv(fastest.reset_index(drop=True), out_dir, "combined_fastest.csv")
    _write_csv(slowest.reset_index(drop=True), out_dir, "combined_slowest.csv")

    full = both.rename(columns=cols)
    _write_csv(full, out_dir, "parkrun_course_grades.csv")


def print_sanity_check(
    course: str,
    time_str: str,
    men: pd.DataFrame,
    women: pd.DataFrame,
) -> None:
    """Print the equivalent time at the fastest-rated course for a given time at a given course."""
    from parkrun.utils import format_time, parse_time_minutes

    your_mins = parse_time_minutes(time_str)
    if your_mins is None:
        print(f"Sanity check: could not parse time '{time_str}'")
        return

    print(f"\nSanity check: {time_str} at {course}")

    for label, df_g in [("Men", men), ("Women", women)]:
        match = df_g[df_g["Event Name"].str.fullmatch(course, case=False, na=False)]
        if match.empty:
            print(f"  {label}: '{course}' not found in dataset")
            continue

        row = match.iloc[0]
        fastest_course = df_g.loc[df_g["factor"].idxmax(), "Event Name"]
        equivalent = format_time(your_mins * row["factor"])
        print(
            f"  {label}: ref {row['p_ref_fmt']}, factor {row['factor']:.4f} → {equivalent} at {fastest_course}"
        )


def _write_csv(df: pd.DataFrame, out_dir: str, filename: str) -> None:
    path = os.path.join(out_dir, filename)
    df.to_csv(path, index=False)
    print(f"Saved {path}")


def main() -> None:
    ref_str, ref_label = _ref_labels(METHOD, PERCENTILE)
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load
    print("Loading data...")
    df = load_data(DATA_PATH)
    print(f"{len(df):,} clean records")

    # Compute
    men, women = compute_stats(df, PERCENTILE, MIN_N, method=METHOD)
    add_speed_factors(men, women)
    both = compute_combined(men, women)

    ref_idx_men = men["p_ref"].idxmin()
    ref_idx_women = women["p_ref"].idxmin()
    corr = both["factor_men"].corr(both["factor_women"])

    print(
        f"Method     : {METHOD}"
        + (f"  ({PERCENTILE:.0%})" if METHOD == "percentile" else "")
    )
    print(f"Courses    : {len(men)} men, {len(women)} women  (min {MIN_N} finishers)")
    print(
        f"Men   reference ({ref_str}): {men.loc[ref_idx_men, 'p_ref_fmt']}  ({men.loc[ref_idx_men, 'Event Name']})"
    )
    print(
        f"Women reference ({ref_str}): {women.loc[ref_idx_women, 'p_ref_fmt']}  ({women.loc[ref_idx_women, 'Event Name']})"
    )
    print(f"M/F factor correlation: {corr:.3f}")

    # Save tables
    save_fastest_tables(men, women, ref_label, METHOD, OUT_DIR)
    save_factor_tables(men, women, ref_label, METHOD, OUT_DIR)
    save_combined_tables(both, OUT_DIR)

    # Save plots
    plot_factors(men, "Male", ref_str, ref_label, OUT_DIR)
    plot_factors(women, "Female", ref_str, ref_label, OUT_DIR)
    plot_mf_sanity(both, corr, OUT_DIR)

    print_sanity_check(SANITY_COURSE, SANITY_TIME, men, women)

    print("\nDone.")


if __name__ == "__main__":
    main()
