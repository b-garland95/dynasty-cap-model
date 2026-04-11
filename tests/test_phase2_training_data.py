"""Tests for Phase 2 training dataset builder."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.modeling.training_data import TRAINING_COLUMNS, build_phase2_training_data


def _make_season_values() -> pd.DataFrame:
    return pd.DataFrame([
        {"season": 2022, "gsis_id": "G-QB1", "player": "QB One", "position": "QB", "rsv": 80.0},
        {"season": 2022, "gsis_id": "G-RB1", "player": "RB One", "position": "RB", "rsv": 60.0},
        {"season": 2022, "gsis_id": "G-WR1", "player": "WR One", "position": "WR", "rsv": 50.0},
        {"season": 2022, "gsis_id": "G-TE1", "player": "TE One", "position": "TE", "rsv": 20.0},
        {"season": 2023, "gsis_id": "G-QB1", "player": "QB One", "position": "QB", "rsv": 75.0},
        {"season": 2023, "gsis_id": "G-RB1", "player": "RB One", "position": "RB", "rsv": 55.0},
        # No gsis_id — should be excluded
        {"season": 2022, "gsis_id": None, "player": "Ghost", "position": "WR", "rsv": 10.0},
        # Null RSV — should be excluded
        {"season": 2022, "gsis_id": "G-WR2", "player": "WR Two", "position": "WR", "rsv": None},
    ])


def _make_rankings() -> pd.DataFrame:
    return pd.DataFrame([
        {"season": 2022, "gsis_id": "G-QB1", "rank": 1},
        {"season": 2022, "gsis_id": "G-RB1", "rank": 5},
        {"season": 2022, "gsis_id": "G-WR1", "rank": 10},
        {"season": 2022, "gsis_id": "G-TE1", "rank": 30},
        {"season": 2023, "gsis_id": "G-QB1", "rank": 2},
        {"season": 2023, "gsis_id": "G-RB1", "rank": 6},
        # No gsis_id — should be excluded
        {"season": 2022, "gsis_id": None, "rank": 99},
        # Player with no matching season_values — should be excluded by inner join
        {"season": 2022, "gsis_id": "G-UNMATCHED", "rank": 200},
    ])


def test_output_columns():
    df = build_phase2_training_data(_make_season_values(), _make_rankings())
    assert list(df.columns) == TRAINING_COLUMNS


def test_inner_join_only_matched():
    df = build_phase2_training_data(_make_season_values(), _make_rankings())
    # 4 matched in 2022 + 2 matched in 2023 = 6
    assert len(df) == 6
    assert set(df["gsis_id"]) == {"G-QB1", "G-RB1", "G-WR1", "G-TE1"}


def test_null_gsis_id_excluded():
    df = build_phase2_training_data(_make_season_values(), _make_rankings())
    assert df["gsis_id"].notna().all()


def test_null_rsv_excluded():
    df = build_phase2_training_data(_make_season_values(), _make_rankings())
    assert "G-WR2" not in df["gsis_id"].values


def test_log_adp_non_negative():
    df = build_phase2_training_data(_make_season_values(), _make_rankings())
    assert (df["log_adp"] >= 0).all()
    # ADP=1 → log(1)=0
    assert np.isclose(df[df["adp"] == 1]["log_adp"].iloc[0], 0.0)


def test_position_filter():
    df = build_phase2_training_data(
        _make_season_values(), _make_rankings(), positions=["QB"]
    )
    assert set(df["position"]) == {"QB"}
    assert len(df) == 2  # QB1 in 2022 + 2023


def test_adp_is_int():
    df = build_phase2_training_data(_make_season_values(), _make_rankings())
    assert df["adp"].dtype == int


def test_sorted_by_season_position_adp():
    df = build_phase2_training_data(_make_season_values(), _make_rankings())
    for season in df["season"].unique():
        for pos in df["position"].unique():
            subset = df[(df["season"] == season) & (df["position"] == pos)]
            if len(subset) > 1:
                assert subset["adp"].is_monotonic_increasing
