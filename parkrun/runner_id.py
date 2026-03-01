"""Reconstruct unique runner IDs from scraped Parkrun results.

Algorithm
---------
The scraped data does not include Parkrun's internal athlete ID, but we can
reconstruct an approximate unique runner identifier from the available columns.

Key Observations
~~~~~~~~~~~~~~~~
1. **Total parkruns** is a *static snapshot* per runner (the same value appears
   on every row for that runner, captured at scrape time). It does NOT increment
   row-by-row.
2. **Name** and **Gender** are also constant per runner.
3. Together, **(Name, Gender, Total parkruns)** forms a fingerprint that
   uniquely identifies the vast majority (~97.6%) of runners.
4. Same-day appearances at *different* events prove two rows belong to
   *different* runners (you can only do one parkrun per Saturday morning).
5. For **first-timers** (Total parkruns == 1), each row is a distinct runner
   by definition (they have exactly one parkrun ever).

Collision Handling
~~~~~~~~~~~~~~~~~~
When multiple rows share the same (Name, Gender, Total parkruns) and appear on
the same date at different events, they must be different runners. We split
these groups using greedy date-partitioning (assign each row to the first
available "slot" that has no date conflict).

Known Limitations
~~~~~~~~~~~~~~~~~
- **Silent collisions**: Two genuinely different runners who share the same
  (Name, Gender, Total parkruns) but *never* run on the same day and have
  compatible age groups will be merged into one ID. This is undetectable
  without external data.
- **Duplicate rows**: The source data contains ~5K duplicate rows (same
  runner, event, date, time appearing twice). These are kept and assigned
  the same Runner_ID (the algorithm treats them as the same person).
- **Age group transitions**: A runner who crosses an age-group boundary
  during the year may show two age groups. This is expected and does NOT
  indicate a collision. ~878 IDs show 3+ age groups, mostly from junior
  runners whose age bands are narrower (JM10, JM11-14, JM15-17).
- **PB values in Time Details are event-specific** (course PBs), not
  overall PBs, so they cannot reliably disambiguate runners across events.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assign_runner_ids(df: pd.DataFrame) -> pd.Series:
    """Assign a unique integer Runner_ID to each row of the dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: Name, Gender, Total parkruns, Event Date,
        Event Name, Age Group.

    Returns
    -------
    pd.Series
        Integer Series aligned with *df.index*, where each value is a unique
        runner identifier.

    Notes
    -----
    The algorithm proceeds in four stages:

    1. **Base grouping** — rows are grouped by (Name, Gender, Total parkruns).
       Each group is tentatively treated as one runner.
    2. **First-timer expansion** — groups where Total parkruns == 1 are
       expanded so that *each row* gets its own ID (one parkrun ever → one
       row per person).
    3. **Conflict splitting** — within each remaining group, rows are split
       into the minimum number of sub-IDs needed so that no sub-ID contains:
       (a) two rows on the same date at different events, or
       (b) rows with incompatible age groups (more than one 5-year band apart,
           or different gender prefixes).
    4. **ID assignment** — each (base_id, sub_id) pair gets a unique integer.
    """
    required = {
        "Name",
        "Gender",
        "Total parkruns",
        "Event Date",
        "Event Name",
        "Age Group",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    key_cols = ["Name", "Gender", "Total parkruns"]

    # --- Stage 1: base group codes ---
    base_id = _base_group_ids(df, key_cols)

    # --- Stage 2: mark first-timers ---
    is_first_timer = df["Total parkruns"] == 1

    # --- Stage 3: detect and split conflicts ---
    runner_id = _split_conflicts(df, base_id, is_first_timer)

    return runner_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _base_group_ids(df: pd.DataFrame, key_cols: list[str]) -> np.ndarray:
    """Return integer group codes for (Name, Gender, Total parkruns)."""
    return df.groupby(key_cols, sort=False).ngroup().values


def _split_conflicts(
    df: pd.DataFrame,
    base_id: np.ndarray,
    is_first_timer: pd.Series,
) -> pd.Series:
    """Split base groups that have same-day or age-group conflicts.

    Returns a pd.Series of final runner IDs aligned with df.index.
    """
    dates = df["Event Date"].values
    events = df["Event Name"].values
    age_groups = df["Age Group"].values
    age_ranges = np.array([_parse_age_range(ag) for ag in age_groups])  # Nx2
    age_lo = age_ranges[:, 0]
    age_hi = age_ranges[:, 1]

    # Build temp frame for non-first-timers
    ft_mask = is_first_timer.values
    non_ft_mask = ~ft_mask
    non_ft_positions = np.where(non_ft_mask)[0]

    # Detect groups with any kind of conflict:
    # (a) same-day at different events, OR
    # (b) age ranges that are incompatible (gap > 1 year)
    non_ft_base = base_id[non_ft_positions]
    non_ft_dates = dates[non_ft_positions]
    non_ft_lo = age_lo[non_ft_positions]
    non_ft_hi = age_hi[non_ft_positions]

    # Find same-day conflict groups
    _temp_df = pd.DataFrame(
        {
            "base_id": non_ft_base,
            "date": non_ft_dates,
        }
    )
    date_counts = _temp_df.groupby(["base_id", "date"]).size()
    date_conflict_ids = set(
        date_counts[date_counts > 1].index.get_level_values("base_id")
    )

    # Find age-group conflict groups
    # A group has an age conflict if the overall range of ages is too wide
    # for one person within a single year.
    # The widest legit range for one person crossing one boundary:
    #   e.g. VM40-44 in Jan → VM45-49 in Dec = span 40..49 = 9
    # So we flag groups where max_hi - min_lo > 9 (span > 9 → must be 2+ people).
    _temp_df2 = pd.DataFrame(
        {
            "base_id": non_ft_base,
            "lo": non_ft_lo,
            "hi": non_ft_hi,
        }
    )
    # Only consider valid age ranges (lo >= 0)
    valid_ages = _temp_df2[_temp_df2["lo"] >= 0]
    if len(valid_ages) > 0:
        age_stats = valid_ages.groupby("base_id").agg(
            min_lo=("lo", "min"),
            max_hi=("hi", "max"),
        )
        age_conflict_ids = set(
            age_stats[age_stats["max_hi"] - age_stats["min_lo"] > 9].index
        )
    else:
        age_conflict_ids = set()

    conflict_base_ids = date_conflict_ids | age_conflict_ids

    # Assign sub-IDs within conflict groups
    sub_id = np.zeros(len(df), dtype=np.int32)

    if conflict_base_ids:
        conflict_mask = np.isin(base_id, list(conflict_base_ids)) & non_ft_mask
        conflict_positions = np.where(conflict_mask)[0]

        if len(conflict_positions) > 0:
            conflict_base = base_id[conflict_positions]
            conflict_dates_arr = dates[conflict_positions]
            conflict_events_arr = events[conflict_positions]
            conflict_lo_arr = age_lo[conflict_positions]
            conflict_hi_arr = age_hi[conflict_positions]

            # Sort by base_id to process groups contiguously
            sort_order = np.argsort(conflict_base)
            sorted_positions = conflict_positions[sort_order]
            sorted_bases = conflict_base[sort_order]
            sorted_dates = conflict_dates_arr[sort_order]
            sorted_events = conflict_events_arr[sort_order]
            sorted_lo = conflict_lo_arr[sort_order]
            sorted_hi = conflict_hi_arr[sort_order]

            # Find group boundaries
            breaks = np.where(sorted_bases[:-1] != sorted_bases[1:])[0] + 1
            starts = np.concatenate([[0], breaks])
            ends = np.concatenate([breaks, [len(sorted_bases)]])

            for s, e in zip(starts, ends):
                group_positions = sorted_positions[s:e]
                group_dates = sorted_dates[s:e]
                group_events = sorted_events[s:e]
                group_lo = sorted_lo[s:e]
                group_hi = sorted_hi[s:e]
                assignments = _greedy_partition(
                    group_dates, group_events, group_lo, group_hi
                )
                for pos, assignment in zip(group_positions, assignments):
                    sub_id[pos] = assignment

    # Compose final runner IDs
    ft_counter = np.zeros(len(df), dtype=np.int64)
    ft_counter[ft_mask] = np.arange(ft_mask.sum())

    composite = pd.DataFrame(
        {
            "base_id": base_id,
            "sub_id": sub_id,
            "ft_seq": ft_counter,
            "is_ft": ft_mask,
        },
        index=df.index,
    )

    composite["key"] = np.where(
        ft_mask,
        composite["base_id"].astype(str) + "_ft_" + composite["ft_seq"].astype(str),
        composite["base_id"].astype(str) + "_" + composite["sub_id"].astype(str),
    )
    runner_id = composite["key"].astype("category").cat.codes

    return pd.Series(runner_id.values, index=df.index, name="Runner_ID")


def _parse_age_range(age_group: str) -> tuple[int, int]:
    """Extract (lower_age, upper_age) from age group string.

    Examples:
        "SM25-29" → (25, 29)
        "VW65-69" → (65, 69)
        "JM10"    → (10, 10)
        "JM11-14" → (11, 14)
        "SM---"   → (-1, -1)  (unparseable)

    Returns (-1, -1) for unparseable values.
    """
    try:
        s = str(age_group)
        num_part = s[2:]  # strip 2-char prefix (SM, SW, VM, VW, JM, JW)
        if num_part == "---" or not num_part:
            return (-1, -1)
        parts = num_part.split("-")
        lo = int(parts[0])
        if len(parts) >= 2 and parts[1]:
            hi = int(parts[1])
        else:
            hi = lo  # e.g. "JM10" → (10, 10)
        return (lo, hi)
    except (ValueError, IndexError):
        return (-1, -1)


def _age_ranges_compatible(lo1: int, hi1: int, lo2: int, hi2: int) -> bool:
    """Check if two age ranges could belong to the same person within 1 year.

    Two ranges are compatible if, accounting for a runner aging at most 1 year,
    the ranges can be bridged.  Concretely: the gap between the ranges must be
    at most 1 year.
    """
    if lo1 < 0 or lo2 < 0:
        return True  # can't determine, assume compatible
    # Gap = lower of higher range - upper of lower range
    gap = max(lo1 - hi2, lo2 - hi1)
    return gap <= 1


def _greedy_partition(
    dates: np.ndarray,
    events: np.ndarray,
    age_lo: np.ndarray,
    age_hi: np.ndarray,
) -> list[int]:
    """Partition rows into minimum sub-groups with no conflicts.

    Two rows conflict if:
    (a) they share the same date but are at different events, OR
    (b) their age ranges are incompatible (gap > 1 year between ranges).

    Rows at the same event on the same date are treated as duplicates of the
    same runner and assigned to the same sub-group.

    Uses a greedy algorithm: sort by date, assign each row to the first
    existing slot that doesn't conflict.

    Parameters
    ----------
    dates : array of dates
    events : array of event names
    age_lo : array of lower age bounds
    age_hi : array of upper age bounds

    Returns
    -------
    list[int]
        Sub-group assignment (0-indexed) for each row.
    """
    order = np.argsort(dates)
    n = len(dates)
    assignments = [0] * n

    # Each slot tracks:
    #   - occupied_dates: {date: event_name}
    #   - min_lo / max_hi: overall age range seen in this slot
    slots: list[dict] = []

    for idx in order:
        d = dates[idx]
        e = events[idx]
        lo = int(age_lo[idx])
        hi = int(age_hi[idx])
        assigned = False

        for slot_id, slot in enumerate(slots):
            # Check date conflict
            if d in slot["dates"] and slot["dates"][d] != e:
                continue  # same date, different event

            # Check age range compatibility
            if lo >= 0 and slot["min_lo"] >= 0:
                if not _age_ranges_compatible(slot["min_lo"], slot["max_hi"], lo, hi):
                    continue  # incompatible age groups

            # Compatible — assign here
            slot["dates"][d] = e
            if lo >= 0:
                slot["min_lo"] = min(slot["min_lo"], lo)
                slot["max_hi"] = max(slot["max_hi"], hi)
            assignments[idx] = slot_id
            assigned = True
            break

        if not assigned:
            slots.append(
                {
                    "dates": {d: e},
                    "min_lo": lo,
                    "max_hi": hi,
                }
            )
            assignments[idx] = len(slots) - 1

    return assignments


# ---------------------------------------------------------------------------
# Validation / diagnostic utilities
# ---------------------------------------------------------------------------


def validate_runner_ids(df: pd.DataFrame, runner_id: pd.Series) -> dict:
    """Run validation checks on assigned runner IDs.

    Returns a dict of test results.
    """
    results = {}
    temp = pd.DataFrame(
        {
            "Runner_ID": runner_id,
            "Event Date": df["Event Date"],
            "Event Name": df["Event Name"],
            "Name": df["Name"],
            "Gender": df["Gender"],
            "Total parkruns": df["Total parkruns"],
            "Age Group": df["Age Group"],
        }
    )

    # Test 1: No runner appears at two different events on the same date
    per_runner_date = temp.groupby(["Runner_ID", "Event Date"])["Event Name"].nunique()
    multi_event = per_runner_date[per_runner_date > 1]
    results["no_same_day_multi_event"] = {
        "passed": len(multi_event) == 0,
        "violations": len(multi_event),
        "description": "No runner ID assigned to different events on the same date",
    }

    # Test 2: Each runner has exactly one Name
    names_per_runner = temp.groupby("Runner_ID")["Name"].nunique()
    multi_name = names_per_runner[names_per_runner > 1]
    results["consistent_name"] = {
        "passed": len(multi_name) == 0,
        "violations": len(multi_name),
        "description": "Each Runner_ID maps to exactly one Name",
    }

    # Test 3: Each runner has exactly one Gender
    gender_per_runner = temp.groupby("Runner_ID")["Gender"].nunique()
    multi_gender = gender_per_runner[gender_per_runner > 1]
    results["consistent_gender"] = {
        "passed": len(multi_gender) == 0,
        "violations": len(multi_gender),
        "description": "Each Runner_ID maps to exactly one Gender",
    }

    # Test 4: Each runner has exactly one Total parkruns value
    tp_per_runner = temp.groupby("Runner_ID")["Total parkruns"].nunique()
    multi_tp = tp_per_runner[tp_per_runner > 1]
    results["consistent_total_parkruns"] = {
        "passed": len(multi_tp) == 0,
        "violations": len(multi_tp),
        "description": "Each Runner_ID maps to exactly one Total parkruns value",
    }

    # Test 5: Age group plausibility — at most 2 age groups per runner
    # (birthday can cause exactly one transition within a year)
    ag_per_runner = temp.groupby("Runner_ID")["Age Group"].nunique()
    many_ag = ag_per_runner[ag_per_runner > 2]
    results["plausible_age_groups"] = {
        "passed": len(many_ag) == 0,
        "violations": len(many_ag),
        "description": "Each Runner_ID has at most 2 age groups (birthday transition)",
    }

    # Test 6: First-timers (Total parkruns == 1) have exactly 1 row
    ft_rows = temp[temp["Total parkruns"] == 1]
    ft_counts = ft_rows.groupby("Runner_ID").size()
    multi_ft = ft_counts[ft_counts > 1]
    results["first_timers_single_row"] = {
        "passed": len(multi_ft) == 0,
        "violations": len(multi_ft),
        "description": "Runners with Total parkruns=1 have exactly 1 row",
    }

    # Summary stats
    n_runners = runner_id.nunique()
    n_rows = len(df)
    results["summary"] = {
        "total_rows": n_rows,
        "unique_runners": n_runners,
        "avg_rows_per_runner": round(n_rows / n_runners, 2),
    }

    return results


def print_validation(results: dict) -> None:
    """Pretty-print validation results."""
    print("=" * 60)
    print("Runner ID Validation Results")
    print("=" * 60)

    for key, val in results.items():
        if key == "summary":
            continue
        status = "PASS" if val["passed"] else f"FAIL ({val['violations']:,} violations)"
        print(f"  [{status}] {val['description']}")

    summary = results["summary"]
    print(f"\n  Total rows:      {summary['total_rows']:>12,}")
    print(f"  Unique runners:  {summary['unique_runners']:>12,}")
    print(f"  Avg rows/runner: {summary['avg_rows_per_runner']:>12.2f}")
    print("=" * 60)
