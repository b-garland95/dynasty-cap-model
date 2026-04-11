"""Generate Phase 2 backtest visuals: forecast vs actuals by position.

Usage:
    python scripts/plot_phase2_backtest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PREDICTIONS_CSV = REPO_ROOT / "data" / "processed" / "phase2_backtest_player_predictions.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "phase2_plots"

POSITIONS = ["QB", "RB", "WR", "TE"]
POS_COLORS = {"QB": "#E24A33", "RB": "#348ABD", "WR": "#988ED5", "TE": "#FBC15E"}


def plot_forecast_vs_actual(preds: pd.DataFrame, output_dir: Path) -> None:
    """Scatter plot of rsv_hat vs actual rsv, one panel per position."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for ax, pos in zip(axes, POSITIONS):
        df = preds[preds["position"] == pos]
        color = POS_COLORS[pos]

        ax.scatter(df["rsv_hat"], df["rsv"], alpha=0.35, s=18, color=color, edgecolors="none")

        # Perfect prediction line
        lo = min(df["rsv"].min(), df["rsv_hat"].min()) - 5
        hi = max(df["rsv"].max(), df["rsv_hat"].max()) + 5
        ax.plot([lo, hi], [lo, hi], "k--", linewidth=0.8, alpha=0.5)

        # Stats annotation
        mae = (df["rsv"] - df["rsv_hat"]).abs().mean()
        rho = df["rsv"].rank().corr(df["rsv_hat"].rank())
        ax.text(
            0.05, 0.95,
            f"n={len(df)}  MAE={mae:.1f}  ρ={rho:.2f}",
            transform=ax.transAxes, fontsize=9, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )

        ax.set_xlabel("Predicted RSV")
        ax.set_ylabel("Actual RSV")
        ax.set_title(pos, fontsize=13, fontweight="bold")
        ax.set_aspect("equal", adjustable="datalim")

    fig.suptitle("Phase 2 Backtest: Predicted vs Actual RSV (2021–2025)", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(output_dir / "forecast_vs_actual_by_position.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_residuals_by_adp(preds: pd.DataFrame, output_dir: Path) -> None:
    """Residual (actual - predicted) vs ADP, with quantile bands, per position."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for ax, pos in zip(axes, POSITIONS):
        df = preds[preds["position"] == pos].sort_values("adp")
        color = POS_COLORS[pos]
        resid = df["rsv"] - df["rsv_hat"]

        ax.scatter(df["adp"], resid, alpha=0.3, s=14, color=color, edgecolors="none")
        ax.axhline(0, color="k", linewidth=0.8, linestyle="--", alpha=0.5)

        # Rolling mean of residuals for trend
        if len(df) > 20:
            roll = pd.DataFrame({"adp": df["adp"].values, "resid": resid.values})
            roll = roll.sort_values("adp")
            smooth = roll["resid"].rolling(window=max(len(roll) // 10, 5), center=True, min_periods=3).mean()
            ax.plot(roll["adp"], smooth, color="black", linewidth=1.5, alpha=0.6, label="rolling mean")

        ax.set_xlabel("ADP")
        ax.set_ylabel("Residual (Actual − Predicted)")
        ax.set_title(pos, fontsize=13, fontweight="bold")

    fig.suptitle("Phase 2 Backtest: Residuals vs ADP (2021–2025)", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(output_dir / "residuals_by_adp.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_calibration_curves(preds: pd.DataFrame, output_dir: Path) -> None:
    """ADP vs RSV with isotonic fit line and p25-p75 band, per position."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for ax, pos in zip(axes, POSITIONS):
        df = preds[preds["position"] == pos].sort_values("adp")
        color = POS_COLORS[pos]

        # Actual RSV scatter
        ax.scatter(df["adp"], df["rsv"], alpha=0.25, s=14, color=color, edgecolors="none", label="Actual RSV")

        # Isotonic fit line (take unique ADP predictions to avoid overplotting)
        fit = df.drop_duplicates(subset=["adp"]).sort_values("adp")
        ax.plot(fit["adp"], fit["rsv_hat"], color="black", linewidth=2, label="Isotonic fit")

        # p25–p75 band
        ax.fill_between(
            fit["adp"], fit["rsv_p25"], fit["rsv_p75"],
            alpha=0.15, color=color, label="p25–p75 band",
        )

        coverage = ((df["rsv"] >= df["rsv_p25"]) & (df["rsv"] <= df["rsv_p75"])).mean()
        ax.text(
            0.95, 0.95,
            f"coverage={coverage:.0%}",
            transform=ax.transAxes, fontsize=9, ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )

        ax.set_xlabel("ADP")
        ax.set_ylabel("RSV")
        ax.set_title(pos, fontsize=13, fontweight="bold")
        ax.legend(fontsize=8, loc="lower left")

    fig.suptitle("Phase 2: ADP → RSV Calibration Curves with Uncertainty (2021–2025)", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(output_dir / "calibration_curves_by_position.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_yearly_metrics(output_dir: Path) -> None:
    """Bar chart of MAE and Spearman by season, faceted by position."""
    summary = pd.read_csv(REPO_ROOT / "data" / "processed" / "phase2_backtest_summary.csv")
    summary = summary[~summary["season"].isin(["OVERALL"])]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, metric, label in [
        (axes[0], "mae", "MAE (RSV)"),
        (axes[1], "spearman_rho", "Spearman ρ"),
    ]:
        pivot = summary[summary["position"] != "ALL"].pivot(
            index="season", columns="position", values=metric,
        )
        pivot = pivot[POSITIONS]
        pivot.plot(
            kind="bar", ax=ax, color=[POS_COLORS[p] for p in POSITIONS],
            width=0.7, edgecolor="none",
        )
        ax.set_ylabel(label)
        ax.set_xlabel("Test Season")
        ax.set_title(label, fontsize=13, fontweight="bold")
        ax.legend(fontsize=9)
        ax.tick_params(axis="x", rotation=0)

    fig.suptitle("Phase 2 Backtest Metrics by Season", fontsize=14, y=1.02)
    fig.tight_layout()
    fig.savefig(output_dir / "yearly_metrics.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    preds = pd.read_csv(PREDICTIONS_CSV)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plot_forecast_vs_actual(preds, OUTPUT_DIR)
    plot_residuals_by_adp(preds, OUTPUT_DIR)
    plot_calibration_curves(preds, OUTPUT_DIR)
    plot_yearly_metrics(OUTPUT_DIR)

    print(f"Wrote 4 plots to {OUTPUT_DIR}/")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        print(f"  {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
