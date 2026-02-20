# Parkrun Analysis

Exploratory analysis of ~9.5 million Parkrun results from 2025 (`Parkrun_2025.parquet`, 238 MB).

## Setup

```bash
uv sync          # installs dependencies + the parkrun package
source .venv/bin/activate
```

## Structure

```
parkrun/                   # shared library — import anywhere
    data.py                # load_data()
    utils.py               # parse_time_minutes(), format_time()

analyses/
    speed_factors/         # course difficulty ratings
        compute.py         # pure computation functions
        plots.py           # plotting functions
        run.py             # entry point + config

results/
    speed-factors/         # saved plots and CSV tables
```

**`parkrun/`** is installed as a package via `uv sync`, so `import parkrun` works in scripts and notebooks alike.

Each analysis lives in its own `analyses/<topic>/` directory. Config (percentile, min runners, output path) is at the top of `run.py`.

## Running an analysis

```bash
python analyses/speed_factors/run.py
```

## Adding a new analysis

1. Create `analyses/<topic>/` with `compute.py`, `plots.py`, `run.py`
2. Import shared utilities from `parkrun`
3. Save outputs to `results/<topic>/`
