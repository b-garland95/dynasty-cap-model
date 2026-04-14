"""Tests for dynasty ADP positional-rank calibration."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.modeling.dynasty_calibration import (
    DYNASTY_TRAINING_COLUMNS,
    build_dynasty_training_data,
    compute_positional_rank,
    fit_dynasty_calibration,
    predict_dynasty_ceiling,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_dynasty_rankings(n_per_pos: int = 5) -> pd.DataFrame:
    """Build a minimal multi-season, multi-position dynasty rankings frame."""
    positions = ["QB", "RB", "WR", "TE"]
    rows = []
    overall_rank = 1
    for season in [2022, 2023]:
        for pos in positions:
            for i in range(n_per_pos):
                rows.append({
                    "season": season,
                    "gsis_id": f"G-{pos}{i+1}",
                    "player": f"{pos} Player {i+1}",
                    "position": pos,
                    "rank": overall_rank,
                    "team": "NFL",
                })
                overall_rank += 1
    return pd.DataFrame(rows)


def _make_season_values(n_per_pos: int = 5) -> pd.DataFrame:
    """Build synthetic Phase 1 season values aligned with the ranking fixture."""
    rng = np.random.default_rng(0)
    positions = ["QB", "RB", "WR", "TE"]
    rows = []
    for season in [2022, 2023]:
        for pos in positions:
            for i in range(n_per_pos):
                rows.append({
                    "season": season,
                    "gsis_id": f"G-{pos}{i+1}",
                    "player": f"{pos} Player {i+1}",
                    "position": pos,
                    "esv": 80.0 - i * 10 + rng.normal(0, 3),
                    "is_rookie": i == 0,
                    "years_of_experience": i,
                    "age": 22.0 + i,
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# compute_positional_rank
# ---------------------------------------------------------------------------

class TestComputePositionalRank:

    def test_adds_dynasty_pos_rank_column(self):
        rankings = _make_dynasty_rankings()
        result = compute_positional_rank(rankings)
        assert "dynasty_pos_rank" in result.columns

    def test_positional_ranks_start_at_one(self):
        rankings = _make_dynasty_rankings(n_per_pos=5)
        result = compute_positional_rank(rankings)
        for (season, pos), grp in result.groupby(["season", "position"]):
            assert grp["dynasty_pos_rank"].min() == 1

    def test_positional_ranks_are_contiguous(self):
        rankings = _make_dynasty_rankings(n_per_pos=5)
        result = compute_positional_rank(rankings)
        for (season, pos), grp in result.groupby(["season", "position"]):
            ranks = sorted(grp["dynasty_pos_rank"].tolist())
            assert ranks == list(range(1, len(grp) + 1))

    def test_positional_rank_ordered_by_overall_rank(self):
        """Player with lower overall rank gets positional rank 1."""
        df = pd.DataFrame([
            {"season": 2022, "position": "WR", "gsis_id": "A", "rank": 5},
            {"season": 2022, "position": "WR", "gsis_id": "B", "rank": 12},
            {"season": 2022, "position": "WR", "gsis_id": "C", "rank": 20},
        ])
        result = compute_positional_rank(df)
        pos_ranks = result.set_index("gsis_id")["dynasty_pos_rank"]
        assert pos_ranks["A"] < pos_ranks["B"] < pos_ranks["C"]
        assert pos_ranks["A"] == 1

    def test_positional_ranks_reset_per_season(self):
        """Position rank 1 exists in each season independently."""
        df = pd.DataFrame([
            {"season": 2022, "position": "RB", "gsis_id": "X", "rank": 1},
            {"season": 2023, "position": "RB", "gsis_id": "X", "rank": 3},
        ])
        result = compute_positional_rank(df)
        for season in [2022, 2023]:
            subset = result[result["season"] == season]
            assert subset["dynasty_pos_rank"].min() == 1

    def test_positional_ranks_separate_per_position(self):
        """QB rank 1 and RB rank 1 can coexist in same season."""
        df = pd.DataFrame([
            {"season": 2022, "position": "QB", "gsis_id": "Q1", "rank": 1},
            {"season": 2022, "position": "RB", "gsis_id": "R1", "rank": 2},
        ])
        result = compute_positional_rank(df)
        assert result.loc[result["gsis_id"] == "Q1", "dynasty_pos_rank"].iloc[0] == 1
        assert result.loc[result["gsis_id"] == "R1", "dynasty_pos_rank"].iloc[0] == 1

    def test_does_not_mutate_input(self):
        rankings = _make_dynasty_rankings()
        original_cols = set(rankings.columns)
        compute_positional_rank(rankings)
        assert set(rankings.columns) == original_cols


# ---------------------------------------------------------------------------
# build_dynasty_training_data
# ---------------------------------------------------------------------------

class TestBuildDynastyTrainingData:

    def test_output_columns(self):
        df = build_dynasty_training_data(_make_season_values(), _make_dynasty_rankings())
        assert list(df.columns) == DYNASTY_TRAINING_COLUMNS

    def test_inner_join_only_matched(self):
        sv = _make_season_values(n_per_pos=5)
        dr = _make_dynasty_rankings(n_per_pos=3)  # fewer ranked players
        df = build_dynasty_training_data(sv, dr)
        # Only players appearing in both frames survive the inner join
        assert df["gsis_id"].isin(dr["gsis_id"].dropna()).all()

    def test_log_adp_equals_log_pos_rank(self):
        df = build_dynasty_training_data(_make_season_values(), _make_dynasty_rankings())
        expected = np.log(df["dynasty_pos_rank"].values)
        np.testing.assert_allclose(df["log_adp"].values, expected)

    def test_log_adp_non_negative(self):
        df = build_dynasty_training_data(_make_season_values(), _make_dynasty_rankings())
        assert (df["log_adp"] >= 0).all()

    def test_dynasty_pos_rank_is_int(self):
        df = build_dynasty_training_data(_make_season_values(), _make_dynasty_rankings())
        assert df["dynasty_pos_rank"].dtype == int

    def test_null_gsis_id_in_rankings_excluded(self):
        dr = _make_dynasty_rankings()
        dr.loc[0, "gsis_id"] = None
        df = build_dynasty_training_data(_make_season_values(), dr)
        assert df["gsis_id"].notna().all()

    def test_null_esv_in_season_values_excluded(self):
        sv = _make_season_values()
        sv.loc[0, "esv"] = None
        df = build_dynasty_training_data(sv, _make_dynasty_rankings())
        assert df["esv"].notna().all()

    def test_position_filter(self):
        df = build_dynasty_training_data(
            _make_season_values(), _make_dynasty_rankings(), positions=["QB"]
        )
        assert set(df["position"]) == {"QB"}

    def test_missing_extra_features_filled_with_nan(self):
        sv = _make_season_values().drop(columns=["is_rookie", "age"])
        df = build_dynasty_training_data(sv, _make_dynasty_rankings())
        assert df["is_rookie"].isna().all()
        assert df["age"].isna().all()

    def test_sorted_by_season_position_pos_rank(self):
        df = build_dynasty_training_data(_make_season_values(), _make_dynasty_rankings())
        for (season, pos), grp in df.groupby(["season", "position"]):
            if len(grp) > 1:
                assert grp["dynasty_pos_rank"].is_monotonic_increasing


# ---------------------------------------------------------------------------
# fit_dynasty_calibration + predict_dynasty_ceiling
# ---------------------------------------------------------------------------

class TestFitDynastyCalibration:

    def _training(self, n_per_pos: int = 40, seed: int = 0) -> pd.DataFrame:
        """Synthetic training with lower pos-rank → higher ESV."""
        rng = np.random.default_rng(seed)
        rows = []
        for pos in ["QB", "RB", "WR", "TE"]:
            for rank in range(1, n_per_pos + 1):
                rows.append({
                    "season": 2022,
                    "gsis_id": f"G-{pos}{rank}",
                    "player": f"{pos} {rank}",
                    "position": pos,
                    "dynasty_pos_rank": rank,
                    "log_adp": np.log(rank),
                    "is_rookie": False,
                    "years_of_experience": 3,
                    "age": 26.0,
                    "esv": 100.0 - 20 * np.log(rank) + rng.normal(0, 5),
                })
        return pd.DataFrame(rows)

    def test_returns_calibrations_for_all_positions(self):
        cals = fit_dynasty_calibration(self._training())
        for pos in ["QB", "RB", "WR", "TE"]:
            assert pos in cals

    def test_predictions_monotone_decreasing(self):
        """Higher positional rank (worse) → lower or equal expected ESV."""
        cals = fit_dynasty_calibration(self._training())
        for pos in ["QB", "RB", "WR", "TE"]:
            test = pd.DataFrame({
                "position": pos,
                "log_adp": np.log(np.arange(1, 30)),
            })
            scored = predict_dynasty_ceiling(cals, test)
            diffs = np.diff(scored["esv_hat"].values)
            assert (diffs <= 1e-10).all(), f"{pos}: monotonicity violated"

    def test_pos_rank_1_beats_pos_rank_20(self):
        cals = fit_dynasty_calibration(self._training())
        for pos in ["QB", "RB", "WR", "TE"]:
            test = pd.DataFrame({
                "position": [pos, pos],
                "log_adp": [np.log(1), np.log(20)],
            })
            scored = predict_dynasty_ceiling(cals, test)
            assert scored.iloc[0]["esv_hat"] >= scored.iloc[1]["esv_hat"]

    def test_predict_adds_band_columns(self):
        cals = fit_dynasty_calibration(self._training())
        test = pd.DataFrame({"position": ["QB"], "log_adp": [0.0]})
        scored = predict_dynasty_ceiling(cals, test)
        for col in ["esv_hat", "esv_p25", "esv_p50", "esv_p75"]:
            assert col in scored.columns

    def test_quantile_ordering(self):
        cals = fit_dynasty_calibration(self._training())
        test = pd.DataFrame({
            "position": ["QB"] * 10,
            "log_adp": np.log(np.arange(1, 11)),
        })
        scored = predict_dynasty_ceiling(cals, test)
        assert (scored["esv_p25"] <= scored["esv_p50"] + 1e-9).all()
        assert (scored["esv_p50"] <= scored["esv_p75"] + 1e-9).all()
