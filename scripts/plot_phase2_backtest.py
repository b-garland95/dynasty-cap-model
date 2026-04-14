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

from src.ingest.historical_weekly_points import get_config_player_positions
from src.utils.config import load_league_config

PREDICTIONS_CSV = REPO_ROOT / "data" / "processed" / "phase2_backtest_player_predictions.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "phase2_plots"

# Colour palette keyed by position name; extend if new positions are added to config.
POS_COLORS = {"QB": "#E24A33", "RB": "#348ABD", "WR": "#988ED5", "TE": "#FBC15E"}


def plot_forecast_vs_actual(preds: pd.DataFrame, output_dir: Path, positions: list[str]) -> None:
    """Scatter plot of esv_hat vs actual esv, one panel per position."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for ax, pos in zip(axes, positions):
        df = preds[preds["position"] == pos]
        color = POS_COLORS[pos]

        ax.scatter(df["esv_hat"], df["esv"], alpha=0.35, s=18, color=color, edgecolors="none")

        # Perfect prediction line
        lo = min(df["esv"].min(), df["esv_hat"].min()) - 5
        hi = max(df["esv"].max(), df["esv_hat"].max()) + 5
        ax.plot([lo, hi], [lo, hi], "k--", linewidth=0.8, alpha=0.5)

        # Stats annotation
        mae = (df["esv"] - df["esv_hat"]).abs().mean()
        rho = df["esv"].rank().corr(df["esv_hat"].rank())
        ax.text(
            0.05, 0.95,
            f"n={len(df)}  MAE={mae:.1f}  ρ={rho:.2f}",
            transform=ax.transAxes, fontsize=9, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )

        ax.set_xlabel("Predicted ESV")
        ax.set_ylabel("Actual ESV")
        ax.set_title(pos, fontsize=13, fontweight="bold")
        ax.set_aspect("equal", adjustable="datalim")

    fig.suptitle("Phase 2 Backtest: Predicted vs Actual ESV (2021–2025)", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(output_dir / "forecast_vs_actual_by_position.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_residuals_by_adp(preds: pd.DataFrame, output_dir: Path, positions: list[str]) -> None:
    """Residual (actual - predicted) vs ADP, with quantile bands, per position."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for ax, pos in zip(axes, positions):
        df = preds[preds["position"] == pos].sort_values("adp")
        color = POS_COLORS[pos]
        resid = df["esv"] - df["esv_hat"]

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


def plot_calibration_curves(preds: pd.DataFrame, output_dir: Path, positions: list[str]) -> None:
    """ADP vs ESV with isotonic fit line and p25-p75 band, per position."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for ax, pos in zip(axes, positions):
        df = preds[preds["position"] == pos].sort_values("adp")
        color = POS_COLORS[pos]

        # Actual ESV scatter
        ax.scatter(df["adp"], df["esv"], alpha=0.25, s=14, color=color, edgecolors="none", label="Actual ESV")

        # Isotonic fit line (take unique ADP predictions to avoid overplotting)
        fit = df.drop_duplicates(subset=["adp"]).sort_values("adp")
        ax.plot(fit["adp"], fit["esv_hat"], color="black", linewidth=2, label="Isotonic fit")

        # p25–p75 band
        ax.fill_between(
            fit["adp"], fit["esv_p25"], fit["esv_p75"],
            alpha=0.15, color=color, label="p25–p75 band",
        )

        coverage = ((df["esv"] >= df["esv_p25"]) & (df["esv"] <= df["esv_p75"])).mean()
        ax.text(
            0.95, 0.95,
            f"coverage={coverage:.0%}",
            transform=ax.transAxes, fontsize=9, ha="right", va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )

        ax.set_xlabel("ADP")
        ax.set_ylabel("ESV")
        ax.set_title(pos, fontsize=13, fontweight="bold")
        ax.legend(fontsize=8, loc="lower left")

    fig.suptitle("Phase 2: ADP → ESV Calibration Curves with Uncertainty (2021–2025)", fontsize=14, y=1.01)
    fig.tight_layout()
    fig.savefig(output_dir / "calibration_curves_by_position.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_yearly_metrics(output_dir: Path, positions: list[str]) -> None:
    """Bar chart of MAE and Spearman by season, faceted by position."""
    summary = pd.read_csv(REPO_ROOT / "data" / "processed" / "phase2_backtest_summary.csv")
    summary = summary[~summary["season"].isin(["OVERALL"])]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, metric, label in [
        (axes[0], "mae", "MAE (ESV)"),
        (axes[1], "spearman_rho", "Spearman ρ"),
    ]:
        pivot = summary[summary["position"] != "ALL"].pivot(
            index="season", columns="position", values=metric,
        )
        pivot = pivot[[p for p in positions if p in pivot.columns]]
        pivot.plot(
            kind="bar", ax=ax, color=[POS_COLORS.get(p, "#999999") for p in pivot.columns],
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
    config = load_league_config()
    positions = get_config_player_positions(config)
    preds = pd.read_csv(PREDICTIONS_CSV)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plot_forecast_vs_actual(preds, OUTPUT_DIR, positions)
    plot_residuals_by_adp(preds, OUTPUT_DIR, positions)
    plot_calibration_curves(preds, OUTPUT_DIR, positions)
    plot_yearly_metrics(OUTPUT_DIR, positions)

    print(f"Wrote 4 plots to {OUTPUT_DIR}/")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        print(f"  {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
