"""Plotting functions for the speed-factors analysis."""

import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd


def plot_factors(
    df_g: pd.DataFrame,
    gender: str,
    pct_str: str,
    pct_label: str,
    out_dir: str,
    n: int = 10,
) -> None:
    """Broken-axis dot plot: n fastest courses on the left, n slowest on the right.

    Right-hand axis shows the percentile time in MM:SS.
    Saved to out_dir/speed_factors_{gender.lower()}.png.
    """
    color = "steelblue" if gender == "Male" else "darkorange"
    p_ref = df_g["p_ref"].min()

    fastest = df_g.nlargest(n, "factor").sort_values("factor", ascending=False)
    slowest = df_g.nsmallest(n, "factor").sort_values("factor", ascending=True)

    fig, (ax_fast, ax_slow) = plt.subplots(
        1, 2, figsize=(18, 6), sharey=True, gridspec_kw={"width_ratios": [1, 1]}
    )
    fig.subplots_adjust(wspace=0.05)

    def _draw_panel(ax: plt.Axes, data: pd.DataFrame) -> None:
        x = np.arange(len(data))
        ax.scatter(x, data["factor"].values, color=color, s=60, zorder=4)
        ax.axhline(1.0, color="grey", lw=0.9, ls="--", alpha=0.7, zorder=1)
        labels = [name.replace(" parkrun", "").strip() for name in data["Event Name"]]
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8.5)
        ax.set_xlim(-0.6, len(data) - 0.4)
        ax.grid(axis="y", alpha=0.3, lw=0.8, color="grey")
        ax.set_axisbelow(True)

    _draw_panel(ax_fast, fastest)
    _draw_panel(ax_slow, slowest)

    ax_fast.set_title("10 Fastest Courses", fontsize=12, pad=8)
    ax_slow.set_title("10 Slowest Courses", fontsize=12, pad=8)
    ax_fast.set_ylabel("Speed Factor  (1.0 = fastest course)", fontsize=11)

    _add_broken_axis_slashes(ax_fast, ax_slow)
    _add_time_secondary_axis(ax_slow, p_ref, pct_label)

    fig.suptitle(
        f"Parkrun Course Speed Factors — {gender}  ({pct_str})",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )
    fig.tight_layout()

    path = os.path.join(out_dir, f"speed_factors_{gender.lower()}.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


def plot_mf_sanity(both: pd.DataFrame, corr: float, out_dir: str) -> None:
    """Two-panel sanity-check plot: M vs F scatter and speed-factor distributions.

    Saved to out_dir/mf_scatter_distribution.png.
    """
    fig, (ax_scatter, ax_hist) = plt.subplots(1, 2, figsize=(14, 5))

    _draw_mf_scatter(ax_scatter, both, corr)
    _draw_factor_histogram(ax_hist, both)

    plt.tight_layout()
    path = os.path.join(out_dir, "mf_scatter_distribution.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved {path}")


# ── Private helpers ────────────────────────────────────────────────────────────


def _add_broken_axis_slashes(ax_left: plt.Axes, ax_right: plt.Axes) -> None:
    """Draw diagonal slashes at the inner edges to indicate a broken axis."""
    d = 0.018
    slash_kwargs = dict(color="k", clip_on=False, lw=2, zorder=10)

    ax_left.spines["right"].set_visible(False)
    for y in (0, 1):
        ax_left.plot([1 - d, 1 + d], [y - d, y + d], transform=ax_left.transAxes, **slash_kwargs)

    ax_right.spines["left"].set_visible(False)
    ax_right.tick_params(which="both", left=False)
    for y in (0, 1):
        ax_right.plot([-d, +d], [y - d, y + d], transform=ax_right.transAxes, **slash_kwargs)


def _add_time_secondary_axis(ax: plt.Axes, p_ref: float, pct_label: str) -> None:
    """Add a right-hand y-axis showing the percentile time in MM:SS."""
    secax = ax.secondary_yaxis(
        "right",
        functions=(
            lambda f: p_ref / np.asarray(f, float),
            lambda t: p_ref / np.asarray(t, float),
        ),
    )

    def _fmt_mmss(x, _):
        m, s = divmod(round(x * 60), 60)
        return f"{m}:{s:02d}"

    secax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_mmss))
    secax.set_ylabel(f"{pct_label} Time  (MM:SS)", fontsize=11)


def _draw_mf_scatter(ax: plt.Axes, both: pd.DataFrame, corr: float) -> None:
    ax.scatter(both["factor_men"], both["factor_women"], alpha=0.35, s=16, color="steelblue", linewidths=0)
    lim = both[["factor_men", "factor_women"]].stack().agg(["min", "max"]).values + [-0.01, 0.01]
    ax.plot(lim, lim, "r--", lw=1.5)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("Men's Speed Factor")
    ax.set_ylabel("Women's Speed Factor")
    ax.set_title(f"M vs F  (r = {corr:.3f})")


def _draw_factor_histogram(ax: plt.Axes, both: pd.DataFrame) -> None:
    bins = np.linspace(both[["factor_men", "factor_women"]].min().min() - 0.01, 1.01, 50)
    ax.hist(both["factor_men"], bins=bins, alpha=0.6, label="Men", color="steelblue", edgecolor="white")
    ax.hist(both["factor_women"], bins=bins, alpha=0.6, label="Women", color="darkorange", edgecolor="white")
    ax.set_xlabel("Speed Factor")
    ax.set_ylabel("Courses")
    ax.set_title("Distribution of Speed Factors")
    ax.legend()
