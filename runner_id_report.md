# Reconstructing Unique Runner IDs

## Problem

The scraped Parkrun dataset has **9.04M rows** and **902K unique names** — but no athlete ID. Common names like "Paul SMITH" (1,620 rows) refer to many different runners. Can we reconstruct a reliable unique runner identifier?

## Key discovery: `Total parkruns` is a static fingerprint

The `Total parkruns` column is **not** a running counter that increments per row. It is a **snapshot** captured at scrape time — the same value appears on every row for a given runner:

| Date | Total parkruns | Event | Age Group | Time |
|------|---------------|-------|-----------|------|
| 2025-01-11 | 51 | Mote Park | VM35-39 | 25:09 |
| 2025-04-05 | 51 | Maidstone River Park | VM35-39 | 21:22 |
| 2025-12-20 | 51 | Maidstone River Park | VM35-39 | 21:07 |

*(Aaron BENTLEY — all 30 rows show `Total parkruns = 51`)*

This makes it a **per-runner constant** — effectively an anonymous fingerprint.

## Algorithm

The implementation lives in `parkrun/runner_id.py` and works in three stages:

### Stage 1: Base grouping
Group all rows by **(Name, Gender, Total parkruns)**. This produces ~1.26M groups and correctly separates the vast majority of runners. For example, on 1 Jan 2025, 14 different "Paul SMITH"s ran — each at a different event with a different `Total parkruns` value (10, 16, 40, 42, 65, 86, …, 407).

### Stage 2: First-timer expansion
Rows with `Total parkruns = 1` represent someone's only parkrun ever, so **each row is a distinct runner** (182,845 first-timers).

### Stage 3: Conflict splitting
Some base groups still contain multiple runners (same name, gender, and total-parkrun count). We detect these via two signals:

- **Same-day conflicts**: A person can only attend one parkrun per Saturday morning. If two rows in a group fall on the same date at *different* events, they must be different people. (~17,600 detectable conflicts in the raw data.)
- **Age-group incompatibility**: If rows in a group span age ranges too wide for a single person within one year (e.g. SW25-29 and VW45-49), they must be different people.

A **greedy date-partitioning** algorithm assigns rows to the minimum number of sub-IDs needed so that no sub-ID has a date or age conflict.

## Assumptions

1. **`Total parkruns` is constant per runner** — verified empirically; no runner shows changing values across dates.
2. **One parkrun per day per runner** — parkrun events run simultaneously on Saturday mornings, so the same person cannot appear at two events on the same date.
3. **Age groups change at most once per year** — a runner crossing one 5-year boundary (e.g. VM40-44 → VM45-49) is expected. Spanning more than one boundary (gap > 1 year between age ranges) indicates a collision.
4. **`Time Details` contains course-specific PBs**, not overall PBs — "First Timer!" means first time at *that event*, and "PB24:31" is the PB at *that course*. This means PBs cannot reliably disambiguate runners across events.

## Results

| Metric | Value |
|--------|-------|
| Total rows | 9,040,767 |
| **Unique runners identified** | **1,296,091** |
| Avg rows per runner | 6.98 |
| Runtime | ~18s |

### Validation

| Test | Result |
|------|--------|
| No runner at two events on the same date | **PASS** |
| Each ID → exactly one Name | **PASS** |
| Each ID → exactly one Gender | **PASS** |
| Each ID → exactly one Total parkruns | **PASS** |
| Each ID → ≤ 2 age groups | 878 violations (0.07%) |
| First-timers have exactly 1 row | **PASS** |

The 878 age-group violations are predominantly junior runners whose age bands are narrower (JM10, JM11-14, JM15-17) and can legitimately span 3 groups in a single year.

### Spot-check: "Paul SMITH"

The algorithm splits 1,620 "Paul SMITH" rows into **137 distinct runners**, correctly separating e.g. a SM25-29 in Birkenhead from a VM65-69 in Wanstead Flats from a SM30-34 running 18-minute times in Penrith.

## Known limitation: silent collisions

Two genuinely different runners who share the same (Name, Gender, Total parkruns) **and** never run on the same day **and** have compatible age groups will be incorrectly merged. This is fundamentally undetectable without external data. The risk is concentrated among common names with low `Total parkruns` values.
