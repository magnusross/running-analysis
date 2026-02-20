# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Exploratory data analysis on a dataset of ~9.5 million scraped Parkrun results from 2025, stored in `Parkrun_2025.parquet` (~238MB).

## Structure

```
parkrun/               # shared library, installed via uv sync
    data.py            # load_data() — loads parquet, parses times, filters implausible records
    utils.py           # parse_time_minutes(), format_time()

analyses/
    speed_factors/     # course difficulty ratings from percentile finish times
        compute.py     # compute_stats(), add_speed_factors(), compute_combined()
        plots.py       # plot_factors(), plot_mf_sanity()
        run.py         # main() entry point; config lives at the top of this file

results/
    speed-factors/     # output CSVs and PNGs
```

`parkrun` is installed as an editable package (`uv sync`) so `import parkrun` works in scripts and notebooks. Each analysis is a self-contained subdirectory under `analyses/`.

## Environment Setup

- Python 3.12, managed with `uv`
- `uv sync` — installs dependencies and the `parkrun` package
- `source .venv/bin/activate`
- Run an analysis: `python analyses/speed_factors/run.py`
- Run a notebook: `jupyter notebook`

## Dependencies

pandas, pyarrow, duckdb, matplotlib, numpy, ipython (see `pyproject.toml`)

## Dataset Schema

The parquet file contains these columns:

| Column | Type | Notes |
|--------|------|-------|
| Event Name | string | Parkrun location name |
| Event Date | object (datetime.date) | Python date objects |
| Event Number | Int64 | Event sequence number at that location |
| Position | Int64 | Finish position |
| Name | string | Runner name (UPPERCASE surname) |
| Gender | string | "Male" / "Female" |
| Gender Position / Gender Total | Int64 | Position and count within gender |
| Age Group | string | e.g. "SM25-29", "VW65-69" (S=Senior, V=Veteran, M=Male, W=Women, then age range) |
| Age Grade % / Age Grade % (detailed) | Float64 | Age-graded performance percentage |
| Time | str | Finish time as "MM:SS" or "H:MM:SS" |
| Time Details | string | ~3k unique values: "New PB!", "First Timer!", or PB reference like "PB18:33" |
| Achievement | string | Only 2 values: "New PB!" or "First Timer!" (nullable) |
| Total parkruns / Total parkruns (detailed) | Int64 | Runner's cumulative parkrun count |
| Volunteer Count | Int64 | Runner's volunteer count |
| Club Membership | string | "25 Club", "50 Club", "100 Club", "250 Club", "500 Club" (nullable) |
| Volunteer Club | string | e.g. "V50" — volunteer milestone (nullable) |
| Club | string | Running club name (nullable) |
| Source Folder / Source File / Full Path | string | Scrape provenance |
| Processing Date | datetime64[ns] | When the data was processed |
| source_file / batch_id | str/int64 | Batch processing metadata |

## Data Cleaning Notes

- The Time column contains some non-time values; filter with `df["Time"].str.contains(":")` before parsing
- To convert Time to numeric minutes: split on ":" and compute `hours*60 + minutes + seconds/60` (or `minutes + seconds/60` for MM:SS)
- Some records show suspiciously fast times (1 minute); these are likely data quality issues
- Nullable columns (Club, Club Membership, Volunteer Club) use pandas `<NA>`
