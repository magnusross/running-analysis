"""Data loading and cleaning for the Parkrun 2025 dataset."""

import pandas as pd

from parkrun.runner_id import assign_runner_ids
from parkrun.utils import parse_time_minutes

# Time bounds (minutes) — sub-12 is impossible; cap at 2 hours
MIN_PLAUSIBLE_MINS = 12
MAX_PLAUSIBLE_MINS = 120


def load_data(path: str = "Parkrun_2025.parquet") -> pd.DataFrame:
    """Load the parquet file, parse finish times, and drop implausible records.

    Returns a DataFrame with an additional 'mins' column (fractional minutes).
    Only Male / Female rows with a valid time in [12, 120] minutes are kept.
    """
    df = pd.read_parquet(path)

    df = df[df["Time"].notna()].copy()
    df["mins"] = df["Time"].apply(parse_time_minutes)

    clean = df["mins"].between(MIN_PLAUSIBLE_MINS, MAX_PLAUSIBLE_MINS) & df[
        "Gender"
    ].isin(["Male", "Female"])
    df = df[clean].copy()

    # Drop exact duplicate rows (same person, event, date, time, etc.)
    subset = [
        "Event Name",
        "Event Date",
        "Name",
        "Gender",
        "Total parkruns",
        "Age Group",
        "Time",
        "Position",
    ]
    df = df.drop_duplicates(subset=subset)

    return df


# Columns that are scraping/processing metadata or redundant duplicates
_DROP_COLS = [
    "Source Folder",
    "Source File",
    "Full Path",
    "Processing Date",
    "source_file",
    "batch_id",
    "Total parkruns (detailed)",
    "Age Grade % (detailed)",
]


def load_clean_data(path: str = "Parkrun_2025.parquet") -> pd.DataFrame:
    """Load data, assign runner IDs, and keep only analysis-ready columns.

    Builds on :func:`load_data` by:
    1. Assigning a ``Runner_ID`` column via the runner-ID algorithm.
    2. Dropping scraping metadata and redundant columns.

    Returns a tidy DataFrame ready for modelling.
    """
    df = load_data(path)
    df["Runner_ID"] = assign_runner_ids(df)
    df = df.drop(columns=[c for c in _DROP_COLS if c in df.columns])
    return df
