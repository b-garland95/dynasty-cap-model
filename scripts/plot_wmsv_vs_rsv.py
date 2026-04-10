"""Scatter plot: WMSV vs RSV_week with Achane 2023 W3 highlighted."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "phase1" / "wmsv_vs_rsv_week.png"


def main() -> int:
    df = pd.read_csv(REPO_ROOT / "data" / "processed" / "phase1" / "phase1_weekly_detail.csv")

    # Only rows with positive wmsv (zero-wmsv rows cluster at origin).
    plot_df = df[df["wmsv"] > 0].copy()

    # Identify the Achane highlight row.
    achane_mask = (
        (plot_df["player"].str.contains("Achane", case=False))
        & (plot_df["season"] == 2023)
        & (plot_df["week"] == 3)
    )

    fig, ax = plt.subplots(figsize=(12, 8))

    # --- Main scatter (all other points) ------------------------------------
    other = plot_df[~achane_mask]
    ax.scatter(
        other["wmsv"],
        other["rsv_week"],
        s=16,
        alpha=0.35,
        color="#5B8DB8",
        edgecolors="none",
        zorder=2,
    )

    # --- Perfect capture reference line (y = x) -----------------------------
    max_val = max(plot_df["wmsv"].max(), plot_df["rsv_week"].max()) * 1.05
    ax.plot([0, max_val], [0, max_val], ls="--", lw=1, color="#999999", zorder=1, label="Perfect capture (RSV = WMSV)")

    # --- Achane highlight ---------------------------------------------------
    achane = plot_df[achane_mask]
    if not achane.empty:
        ax.scatter(
            achane["wmsv"],
            achane["rsv_week"],
            s=120,
            color="#E24A33",
            edgecolors="black",
            linewidths=1.2,
            zorder=5,
        )
        row = achane.iloc[0]
        ax.annotate(
            f"De'Von Achane\n2023 W3\n{row['points']:.0f} pts, \u03c3={row['start_prob']:.2f}",
            xy=(row["wmsv"], row["rsv_week"]),
            xytext=(row["wmsv"] + 2.5, row["rsv_week"] + 6),
            fontsize=9,
            fontweight="bold",
            color="#E24A33",
            arrowprops=dict(arrowstyle="->, head_width=0.3", color="#E24A33", lw=1.5),
            zorder=6,
        )

    # --- Label other notable points -----------------------------------------
    # Pick points with large wmsv AND large capture gap (wmsv - rsv_week).
    plot_df["_gap"] = plot_df["wmsv"] - plot_df["rsv_week"]
    plot_df["_label"] = plot_df["player"] + " " + plot_df["season"].astype(str) + " W" + plot_df["week"].astype(str)

    # Candidates: high wmsv with big gap, or very high wmsv with high capture.
    candidates = plot_df[~achane_mask & (plot_df["wmsv"] > 15)].copy()
    candidates["_score"] = candidates["_gap"] * 0.6 + candidates["wmsv"] * 0.4

    # Greedy label placement: only label points that are far enough apart.
    candidates = candidates.sort_values("_score", ascending=False)
    labeled_positions: list[tuple[float, float]] = []
    min_dist = 4.0  # minimum distance between labels

    for _, row in candidates.iterrows():
        if achane_mask.any() and row["_label"].startswith("De'Von Achane"):
            continue
        x, y = row["wmsv"], row["rsv_week"]
        too_close = any(
            np.sqrt((x - lx) ** 2 + (y - ly) ** 2) < min_dist
            for lx, ly in labeled_positions
        )
        if too_close:
            continue
        if len(labeled_positions) >= 15:
            break

        ax.annotate(
            row["_label"],
            xy=(x, y),
            xytext=(x + 1.5, y - 2.5),
            fontsize=7,
            color="#333333",
            arrowprops=dict(arrowstyle="-", color="#999999", lw=0.5),
            zorder=4,
        )
        labeled_positions.append((x, y))

    # --- Formatting ---------------------------------------------------------
    ax.set_xlabel("WMSV (Weekly Margin Start Value — perfect capture)", fontsize=11)
    ax.set_ylabel("RSV Week (Rational Start Value — \u03c3-weighted)", fontsize=11)
    ax.set_title("WMSV vs RSV Week: How Much Value Does a Rational Owner Actually Capture?", fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlim(0, max_val)
    ax.set_ylim(0, max_val)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.2)

    fig.tight_layout()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"Saved to {OUTPUT_PATH}")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())