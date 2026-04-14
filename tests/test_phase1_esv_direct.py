"""Direct unit tests for phase1_esv: compute_esv_ld_from_started_weekly and compute_capture_gap."""

from __future__ import annotations

import math

import pandas as pd

from src.valuation.capture_model import FixedProbCaptureModel, PerfectCaptureModel
from src.valuation.phase1_esv import (
    compute_capture_gap,
    compute_esv_ld_from_started_weekly,
    compute_esv_ld_weekly,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _started_weekly(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal started_weekly DataFrame from row dicts."""
    required = {"gsis_id", "player", "position", "season", "week", "margin", "wmsv", "wdrag"}
    for r in rows:
        for col in required:
            if col not in r:
                raise ValueError(f"Row missing column {col!r}: {r}")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# compute_esv_ld_weekly under PerfectCaptureModel
# ---------------------------------------------------------------------------

def test_esv_ld_weekly_under_perfect_capture_esv_equals_margin():
    """Under PerfectCaptureModel: esv_week = 1 × 1 × margin = margin."""
    df = _started_weekly([
        {"season": 2024, "week": 1, "gsis_id": "A", "player": "A", "position": "RB",
         "margin": 5.0, "wmsv": 5.0, "wdrag": 0.0},
        {"season": 2024, "week": 1, "gsis_id": "B", "player": "B", "position": "RB",
         "margin": -3.0, "wmsv": 0.0, "wdrag": -3.0},
    ])
    result = compute_esv_ld_weekly(df, PerfectCaptureModel())

    assert math.isclose(float(result.loc[result["gsis_id"] == "A", "esv_week"].iloc[0]), 5.0)
    assert math.isclose(float(result.loc[result["gsis_id"] == "B", "esv_week"].iloc[0]), -3.0)


def test_esv_ld_weekly_ld_equals_negative_wdrag():
    """Under PerfectCaptureModel: ld_week = roster_prob × start_prob × wdrag."""
    df = _started_weekly([
        {"season": 2024, "week": 1, "gsis_id": "A", "player": "A", "position": "QB",
         "margin": -4.0, "wmsv": 0.0, "wdrag": -4.0},
    ])
    result = compute_esv_ld_weekly(df, PerfectCaptureModel())
    assert math.isclose(float(result["ld_week"].iloc[0]), -4.0)


# ---------------------------------------------------------------------------
# compute_esv_ld_from_started_weekly
# ---------------------------------------------------------------------------

def test_esv_from_started_weekly_is_sum_of_esv_week():
    """Season ESV = sum of weekly esv_week for each player."""
    df = _started_weekly([
        {"season": 2024, "week": 1, "gsis_id": "A", "player": "A", "position": "RB",
         "margin": 5.0, "wmsv": 5.0, "wdrag": 0.0},
        {"season": 2024, "week": 2, "gsis_id": "A", "player": "A", "position": "RB",
         "margin": 3.0, "wmsv": 3.0, "wdrag": 0.0},
        {"season": 2024, "week": 1, "gsis_id": "B", "player": "B", "position": "RB",
         "margin": -2.0, "wmsv": 0.0, "wdrag": -2.0},
    ])
    result = compute_esv_ld_from_started_weekly(df, PerfectCaptureModel())

    esv_a = float(result.loc[result["gsis_id"] == "A", "esv"].iloc[0])
    esv_b = float(result.loc[result["gsis_id"] == "B", "esv"].iloc[0])

    # Under PerfectCaptureModel: esv = sum of margins
    assert math.isclose(esv_a, 5.0 + 3.0, abs_tol=1e-9)
    assert math.isclose(esv_b, -2.0, abs_tol=1e-9)


def test_esv_lte_sav_under_perfect_capture_for_non_negative_margins():
    """When all margins are non-negative, ESV = SAV under PerfectCaptureModel."""
    df = _started_weekly([
        {"season": 2024, "week": 1, "gsis_id": "P1", "player": "P1", "position": "WR",
         "margin": 4.0, "wmsv": 4.0, "wdrag": 0.0},
        {"season": 2024, "week": 2, "gsis_id": "P1", "player": "P1", "position": "WR",
         "margin": 2.0, "wmsv": 2.0, "wdrag": 0.0},
    ])
    result = compute_esv_ld_from_started_weekly(df, PerfectCaptureModel())
    esv = float(result["esv"].iloc[0])
    # wmsv = margin when margin > 0, so ESV = SAV = 4+2 = 6
    assert math.isclose(esv, 6.0, abs_tol=1e-9)


def test_cg_is_zero_for_positive_margins_under_perfect_capture():
    """CG = SAV - ESV = 0 when all margins are positive under PerfectCaptureModel."""
    df = _started_weekly([
        {"season": 2024, "week": 1, "gsis_id": "P1", "player": "P1", "position": "QB",
         "margin": 6.0, "wmsv": 6.0, "wdrag": 0.0},
    ])
    esv_df = compute_esv_ld_from_started_weekly(df, PerfectCaptureModel())
    # Build a minimal sav_df
    sav_df = pd.DataFrame([{"season": 2024, "gsis_id": "P1", "sav": 6.0}])
    cg_df = compute_capture_gap(sav_df, esv_df)
    assert math.isclose(float(cg_df["cg"].iloc[0]), 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# compute_capture_gap
# ---------------------------------------------------------------------------

def test_fixed_prob_zero_start_produces_zero_esv():
    """FixedProbCaptureModel(start_prob=0.0) — no-projection fallback — gives ESV=0 and LD=0."""
    df = _started_weekly([
        {"season": 2024, "week": 1, "gsis_id": "P1", "player": "P1", "position": "RB",
         "margin": 8.0, "wmsv": 8.0, "wdrag": 0.0},
        {"season": 2024, "week": 1, "gsis_id": "P2", "player": "P2", "position": "WR",
         "margin": -4.0, "wmsv": 0.0, "wdrag": -4.0},
    ])
    result = compute_esv_ld_from_started_weekly(df, FixedProbCaptureModel(start_prob=0.0))

    assert math.isclose(float(result.loc[result["gsis_id"] == "P1", "esv"].iloc[0]), 0.0)
    assert math.isclose(float(result.loc[result["gsis_id"] == "P2", "esv"].iloc[0]), 0.0)
    assert math.isclose(float(result.loc[result["gsis_id"] == "P1", "ld"].iloc[0]), 0.0)
    assert math.isclose(float(result.loc[result["gsis_id"] == "P2", "ld"].iloc[0]), 0.0)


def test_capture_gap_cg_equals_sav_minus_esv():
    """CG = SAV - ESV exactly, regardless of sign."""
    sav_df = pd.DataFrame([
        {"season": 2024, "gsis_id": "A", "sav": 10.0},
        {"season": 2024, "gsis_id": "B", "sav": 3.0},
    ])
    esv_df = pd.DataFrame([
        {"season": 2024, "gsis_id": "A", "esv": 7.0, "ld": 0.0},
        {"season": 2024, "gsis_id": "B", "esv": 5.0, "ld": 0.0},
    ])
    cg_df = compute_capture_gap(sav_df, esv_df)
    assert math.isclose(float(cg_df.loc[cg_df["gsis_id"] == "A", "cg"].iloc[0]), 3.0)
    assert math.isclose(float(cg_df.loc[cg_df["gsis_id"] == "B", "cg"].iloc[0]), -2.0)
