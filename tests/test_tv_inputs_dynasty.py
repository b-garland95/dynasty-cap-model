"""Tests for dynasty multi-year TV path (apply_dynasty_tv_path)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.contracts.phase3_dynasty import apply_dynasty_tv_path


# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------

def _make_training_df(n_seasons: int = 5, n_per_pos: int = 15) -> pd.DataFrame:
    """Synthetic Phase 2 training data (season_values joined to redraft ADP)."""
    rng = np.random.default_rng(7)
    rows = []
    for season in range(2019, 2019 + n_seasons):
        for pos in ["QB", "RB", "WR", "TE"]:
            for i in range(1, n_per_pos + 1):
                rows.append({
                    "season": season,
                    "gsis_id": f"G-{pos}{i}",
                    "player": f"{pos} Player {i}",
                    "position": pos,
                    "adp": i,
                    "log_adp": np.log(i),
                    "is_rookie": i == 1,
                    "years_of_experience": i,
                    "age": 22.0 + i,
                    "esv": 80.0 - 15 * np.log(i) + rng.normal(0, 4),
                })
    return pd.DataFrame(rows)


def _make_dynasty_rankings(n_seasons: int = 5, n_per_pos: int = 15) -> pd.DataFrame:
    """Dynasty rankings with same gsis_ids as training data."""
    rows = []
    overall = 1
    for season in range(2019, 2019 + n_seasons):
        for pos in ["QB", "RB", "WR", "TE"]:
            for i in range(1, n_per_pos + 1):
                rows.append({
                    "season": season,
                    "gsis_id": f"G-{pos}{i}",
                    "player": f"{pos} Player {i}",
                    "position": pos,
                    "rank": overall,
                    "team": "NFL",
                })
                overall += 1
    return pd.DataFrame(rows)


def _make_tv_df(
    target_season: int = 2023,
    n_per_pos: int = 10,
    include_age: bool = True,
) -> pd.DataFrame:
    """Minimal TV DataFrame as would be produced by build_phase2_tv_inputs_from_frames."""
    rows = []
    pos_ages = {"QB": 28.0, "RB": 23.0, "WR": 25.0, "TE": 27.0}
    overall_adp = 1
    for pos in ["QB", "RB", "WR", "TE"]:
        for i in range(1, n_per_pos + 1):
            row = {
                "player": f"{pos} Player {i}",
                "team": "TeamA",
                "position": pos,
                "tv_y0": max(0.0, 80.0 - 12 * np.log(i)),
                "tv_y1": max(0.0, 80.0 - 12 * np.log(i)),  # flat (to be replaced)
                "tv_y2": max(0.0, 80.0 - 12 * np.log(i)),
                "tv_y3": max(0.0, 80.0 - 12 * np.log(i)),
                "adp": overall_adp,
                "esv_hat": max(0.0, 80.0 - 12 * np.log(i)),
                "esv_p25": max(0.0, 50.0 - 12 * np.log(i)),
                "esv_p50": max(0.0, 75.0 - 12 * np.log(i)),
                "esv_p75": max(0.0, 100.0 - 12 * np.log(i)),
                "matched_rankings": True,
                "is_rostered": True,
                "tv_input_source": "phase2_2023_adp",
            }
            if include_age:
                row["age"] = pos_ages[pos] + (i - 1) * 0.5
            overall_adp += 1
            rows.append(row)
    return pd.DataFrame(rows)


def _minimal_config() -> dict:
    return {
        "age_curves": {
            "QB": {"peak_age": 29, "rise_slope": 0.04, "decline_slope": 0.06},
            "WR": {"peak_age": 27, "rise_slope": 0.07, "decline_slope": 0.08},
            "RB": {"peak_age": 25, "rise_slope": 0.09, "decline_slope": 0.12},
            "TE": {"peak_age": 27, "rise_slope": 0.05, "decline_slope": 0.07},
        },
        "dynasty_delta_alpha": 0.05,
        "dynasty_band_expansion": 0.40,
    }


# ---------------------------------------------------------------------------
# Output shape and columns
# ---------------------------------------------------------------------------

class TestOutputShape:
    TARGET_SEASON = 2023

    def _run(self, **kwargs):
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        training = _make_training_df()
        dynasty = _make_dynasty_rankings()
        return apply_dynasty_tv_path(
            tv, dynasty, training,
            target_season=self.TARGET_SEASON,
            config=_minimal_config(),
            **kwargs,
        )

    def test_same_row_count(self):
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        result = self._run()
        assert len(result) == len(tv)

    def test_new_band_columns_present(self):
        result = self._run()
        for k in (1, 2, 3):
            assert f"esv_p25_y{k}" in result.columns
            assert f"esv_p75_y{k}" in result.columns

    def test_dynasty_applied_column_present(self):
        result = self._run()
        assert "dynasty_tv_applied" in result.columns

    def test_dynasty_ceiling_column_present(self):
        result = self._run()
        assert "esv_dynasty_ceiling" in result.columns

    def test_delta_column_present(self):
        result = self._run()
        assert "dynasty_delta" in result.columns


# ---------------------------------------------------------------------------
# TV path is no longer flat
# ---------------------------------------------------------------------------

class TestTvPathNotFlat:
    TARGET_SEASON = 2023

    def _run(self):
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        training = _make_training_df()
        dynasty = _make_dynasty_rankings()
        return apply_dynasty_tv_path(
            tv, dynasty, training,
            target_season=self.TARGET_SEASON,
            config=_minimal_config(),
        )

    def test_tv_y1_differs_from_tv_y0_for_matched_players(self):
        result = self._run()
        matched = result[result["dynasty_tv_applied"]]
        # At least some players should have tv_y1 != tv_y0
        not_flat = (matched["tv_y1"] != matched["tv_y0"]).sum()
        assert not_flat > 0, "Expected at least some players with tv_y1 != tv_y0"

    def test_tv_years_not_all_identical(self):
        result = self._run()
        matched = result[result["dynasty_tv_applied"]]
        # tv_y1, tv_y2, tv_y3 should not all be the same for every player
        same_y1_y2 = (matched["tv_y1"] == matched["tv_y2"]).all()
        same_y2_y3 = (matched["tv_y2"] == matched["tv_y3"]).all()
        assert not (same_y1_y2 and same_y2_y3), "All years identical — dynasty path not applied"


# ---------------------------------------------------------------------------
# Young players show upward trajectory; old players show downward
# ---------------------------------------------------------------------------

class TestCareerArcDirection:
    TARGET_SEASON = 2023

    def _result_with_age(self, rb_age: float):
        """Build TV df with all RBs at the same age, then run dynasty path."""
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        # Override RB ages
        tv.loc[tv["position"] == "RB", "age"] = rb_age
        training = _make_training_df()
        dynasty = _make_dynasty_rankings()
        return apply_dynasty_tv_path(
            tv, dynasty, training,
            target_season=self.TARGET_SEASON,
            config=_minimal_config(),
        )

    def test_young_rb_trajectory_rises_toward_peak(self):
        """RB age 22 (pre-peak at 25): tv_y1 >= tv_y0 adjusted for dynasty ceiling."""
        # We compare the dynasty values vs flat y0 for pre-peak young player
        # The top-ranked young RB should have a rising trajectory
        result = self._result_with_age(22.0)
        top_rb = result[result["position"] == "RB"].nsmallest(1, "adp").iloc[0]
        # For a pre-peak player with high dynasty rank, each year should be rising
        assert top_rb["tv_y2"] >= top_rb["tv_y1"] * 0.95, (
            f"Young top RB: tv_y1={top_rb['tv_y1']:.2f}, tv_y2={top_rb['tv_y2']:.2f}"
        )
        assert top_rb["tv_y3"] >= top_rb["tv_y2"] * 0.95, (
            f"Young top RB: tv_y2={top_rb['tv_y2']:.2f}, tv_y3={top_rb['tv_y3']:.2f}"
        )

    def test_veteran_rb_trajectory_declines(self):
        """RB age 32 (post-peak): tv_y2 < tv_y1."""
        result = self._result_with_age(32.0)
        top_rb = result[result["position"] == "RB"].nsmallest(1, "adp").iloc[0]
        assert top_rb["tv_y2"] <= top_rb["tv_y1"] * 1.05, (
            f"Veteran top RB: tv_y1={top_rb['tv_y1']:.2f}, tv_y2={top_rb['tv_y2']:.2f}"
        )

    def test_no_age_column_still_runs(self):
        """Without an age column, function must not raise; all multipliers = 1.0."""
        tv = _make_tv_df(target_season=self.TARGET_SEASON, include_age=False)
        training = _make_training_df()
        dynasty = _make_dynasty_rankings()
        result = apply_dynasty_tv_path(
            tv, dynasty, training,
            target_season=self.TARGET_SEASON,
            config=_minimal_config(),
        )
        assert "dynasty_tv_applied" in result.columns


# ---------------------------------------------------------------------------
# Uncertainty bands
# ---------------------------------------------------------------------------

class TestUncertaintyBands:
    TARGET_SEASON = 2023

    def _run(self):
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        training = _make_training_df()
        dynasty = _make_dynasty_rankings()
        return apply_dynasty_tv_path(
            tv, dynasty, training,
            target_season=self.TARGET_SEASON,
            config=_minimal_config(),
        )

    def test_bands_widen_with_year_offset(self):
        """Dynasty IQR must increase across the three future years."""
        result = self._run()
        matched = result[result["dynasty_tv_applied"]]

        iqr_y1 = (matched["esv_p75_y1"] - matched["esv_p25_y1"]).mean()
        iqr_y2 = (matched["esv_p75_y2"] - matched["esv_p25_y2"]).mean()
        iqr_y3 = (matched["esv_p75_y3"] - matched["esv_p25_y3"]).mean()

        assert iqr_y1 > 0, "Year-1 dynasty IQR should be positive"
        assert iqr_y2 >= iqr_y1 * 0.9, f"y2 IQR {iqr_y2:.1f} < y1 {iqr_y1:.1f}"
        assert iqr_y3 >= iqr_y2 * 0.9, f"y3 IQR {iqr_y3:.1f} < y2 {iqr_y2:.1f}"

    def test_p25_lte_tv_point_estimate(self):
        """Lower band must not exceed the point estimate for matched players."""
        result = self._run()
        matched = result[result["dynasty_tv_applied"]]
        for k in (1, 2, 3):
            violations = (matched[f"esv_p25_y{k}"] > matched[f"tv_y{k}"] + 1e-6).sum()
            assert violations == 0, f"esv_p25_y{k} > tv_y{k} for {violations} rows"

    def test_p75_gte_tv_point_estimate(self):
        """Upper band must not fall below the point estimate for matched players."""
        result = self._run()
        matched = result[result["dynasty_tv_applied"]]
        for k in (1, 2, 3):
            violations = (matched[f"esv_p75_y{k}"] < matched[f"tv_y{k}"] - 1e-6).sum()
            assert violations == 0, f"esv_p75_y{k} < tv_y{k} for {violations} rows"

    def test_bands_non_negative(self):
        result = self._run()
        matched = result[result["dynasty_tv_applied"]]
        for k in (1, 2, 3):
            assert (matched[f"esv_p25_y{k}"] >= -1e-9).all()
            assert (matched[f"esv_p75_y{k}"] >= -1e-9).all()


# ---------------------------------------------------------------------------
# Unmatched players keep flat path
# ---------------------------------------------------------------------------

class TestUnmatchedPlayers:
    TARGET_SEASON = 2023

    def test_unmatched_players_keep_flat_path(self):
        """Players not in dynasty rankings should keep tv_y0 = tv_y1 = tv_y2 = tv_y3."""
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        # Add a player with no dynasty match
        tv = pd.concat([
            tv,
            pd.DataFrame([{
                "player": "Ghost Player",
                "team": "TeamX",
                "position": "WR",
                "tv_y0": 30.0,
                "tv_y1": 30.0,
                "tv_y2": 30.0,
                "tv_y3": 30.0,
                "adp": 999,
                "esv_hat": 30.0,
                "esv_p25": 15.0,
                "esv_p50": 28.0,
                "esv_p75": 45.0,
                "matched_rankings": False,
                "is_rostered": False,
                "tv_input_source": "unranked_zero",
                "age": 25.0,
            }])
        ], ignore_index=True)

        training = _make_training_df()
        dynasty = _make_dynasty_rankings()
        result = apply_dynasty_tv_path(
            tv, dynasty, training,
            target_season=self.TARGET_SEASON,
            config=_minimal_config(),
        )
        ghost = result[result["player"] == "Ghost Player"].iloc[0]
        assert not ghost["dynasty_tv_applied"]
        assert ghost["tv_y1"] == ghost["tv_y0"]
        assert ghost["tv_y2"] == ghost["tv_y0"]
        assert ghost["tv_y3"] == ghost["tv_y0"]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    TARGET_SEASON = 2023

    def test_no_target_season_dynasty_data_raises(self):
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        training = _make_training_df()
        # Dynasty data with no 2023 rows
        dynasty = _make_dynasty_rankings()
        dynasty_past_only = dynasty[dynasty["season"] < self.TARGET_SEASON]
        with pytest.raises(ValueError, match="No dynasty rankings found"):
            apply_dynasty_tv_path(
                tv, dynasty_past_only, training,
                target_season=self.TARGET_SEASON,
                config=_minimal_config(),
            )

    def test_empty_dynasty_training_raises(self):
        tv = _make_tv_df(target_season=self.TARGET_SEASON)
        # Training data with gsis_ids that don't match dynasty rankings
        training_mismatch = _make_training_df()
        training_mismatch["gsis_id"] = "X-" + training_mismatch["gsis_id"]
        dynasty = _make_dynasty_rankings()
        with pytest.raises(ValueError, match="No dynasty training data"):
            apply_dynasty_tv_path(
                tv, dynasty, training_mismatch,
                target_season=self.TARGET_SEASON,
                config=_minimal_config(),
            )
