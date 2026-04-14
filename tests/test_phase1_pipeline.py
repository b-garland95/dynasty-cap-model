"""Tests for the Phase 1 pipeline orchestrator."""

import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.phase1_metrics import compute_dollar_values
from src.valuation.phase1_pipeline import run_phase1_season


def _make_season_data(season: int = 2024) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build minimal synthetic season data (2 weeks) for pipeline testing."""
    pts_rows: list[dict] = []
    proj_rows: list[dict] = []
    adp_rows: list[dict] = []
    rank = 1

    for week in [14, 15]:
        for i in range(1, 13):
            base = {"season": season, "week": week, "gsis_id": f"G-QB{i}", "player": f"QB{i}", "position": "QB"}
            pts_rows.append({**base, "points": float(201 - i - (week - 14))})
            proj_rows.append({**base, "projected_points": float(201 - i)})
            if week == 14:
                adp_rows.append({**{k: v for k, v in base.items() if k != "week"}, "rank": rank})
                rank += 1

        for i in range(1, 31):
            base = {"season": season, "week": week, "gsis_id": f"G-RB{i}", "player": f"RB{i}", "position": "RB"}
            pts_rows.append({**base, "points": float(151 - i - (week - 14))})
            proj_rows.append({**base, "projected_points": float(151 - i)})
            if week == 14:
                adp_rows.append({**{k: v for k, v in base.items() if k != "week"}, "rank": rank})
                rank += 1

        for i in range(1, 46):
            base = {"season": season, "week": week, "gsis_id": f"G-WR{i}", "player": f"WR{i}", "position": "WR"}
            pts_rows.append({**base, "points": float(121 - i - (week - 14))})
            proj_rows.append({**base, "projected_points": float(121 - i)})
            if week == 14:
                adp_rows.append({**{k: v for k, v in base.items() if k != "week"}, "rank": rank})
                rank += 1

        for i in range(1, 19):
            base = {"season": season, "week": week, "gsis_id": f"G-TE{i}", "player": f"TE{i}", "position": "TE"}
            pts_rows.append({**base, "points": float(81 - i - (week - 14))})
            proj_rows.append({**base, "projected_points": float(81 - i)})
            if week == 14:
                adp_rows.append({**{k: v for k, v in base.items() if k != "week"}, "rank": rank})
                rank += 1

    return pd.DataFrame(pts_rows), pd.DataFrame(proj_rows), pd.DataFrame(adp_rows)


def test_run_phase1_season_returns_expected_keys():
    config = load_league_config()
    pts, proj, adp = _make_season_data()

    result = run_phase1_season(pts, proj, adp, config)

    assert set(result.keys()) == {"started_weekly", "sav", "esv_ld", "cg", "par", "cutlines"}
    for key, df in result.items():
        assert isinstance(df, pd.DataFrame), f"{key} is not a DataFrame"
        assert len(df) > 0, f"{key} is empty"


def test_run_phase1_season_cg_equals_sav_minus_esv():
    config = load_league_config()
    pts, proj, adp = _make_season_data()

    result = run_phase1_season(pts, proj, adp, config)
    cg_df = result["cg"]

    for _, row in cg_df.iterrows():
        expected_cg = row["sav"] - row["esv"]
        assert math.isclose(row["cg"], expected_cg, abs_tol=1e-9), (
            f"{row.get('player', '?')}: CG={row['cg']:.6f} != SAV-ESV={expected_cg:.6f}"
        )


def test_run_phase1_season_esv_lte_sav():
    config = load_league_config()
    pts, proj, adp = _make_season_data()

    result = run_phase1_season(pts, proj, adp, config)
    cg_df = result["cg"]

    for _, row in cg_df.iterrows():
        assert row["esv"] <= row["sav"] + 1e-9, (
            f"{row.get('player', '?')}: ESV={row['esv']:.4f} > SAV={row['sav']:.4f}"
        )


def test_run_phase1_season_gsis_id_in_outputs():
    config = load_league_config()
    pts, proj, adp = _make_season_data()

    result = run_phase1_season(pts, proj, adp, config)

    for key in ("sav", "esv_ld", "cg", "par"):
        assert "gsis_id" in result[key].columns, f"gsis_id missing from {key}"


def test_run_phase1_season_no_projections_uses_perfect_capture():
    """With no projections, CG = -LD under PerfectCaptureModel.

    ESV = sum(start_prob × margin) = sum(margin) under perfect capture,
    while SAV = sum(wmsv) = sum(max(0, margin)). So CG = SAV - ESV = -LD.
    """
    config = load_league_config()
    pts, _, _ = _make_season_data()

    result = run_phase1_season(pts, None, None, config)
    cg_df = result["cg"]

    for _, row in cg_df.iterrows():
        assert math.isclose(row["cg"], -row["ld"], abs_tol=1e-9), (
            f"{row.get('player', '?')}: CG={row['cg']:.6f} != -LD={-row['ld']:.6f}"
        )


def test_run_phase1_season_with_rankings_currently_matches_start_only_capture():
    config = load_league_config()
    pts, proj, adp = _make_season_data()

    result_with_rankings = run_phase1_season(pts, proj, adp, config)
    result_without_rankings = run_phase1_season(pts, proj, None, config)

    merged = result_with_rankings["esv_ld"].merge(
        result_without_rankings["esv_ld"],
        on=["season", "gsis_id"],
        suffixes=("_with_adp", "_no_adp"),
    )
    assert merged["esv_with_adp"].equals(merged["esv_no_adp"])
    assert merged["ld_with_adp"].equals(merged["ld_no_adp"])


def _build_season_values_for_test(result: dict, config: dict) -> pd.DataFrame:
    """Helper: assemble the same season_values frame that run_phase1.py builds."""
    cg_df = result["cg"]
    par_df = result["par"]
    return cg_df.merge(
        par_df[["season", "gsis_id", "par"]],
        on=["season", "gsis_id"],
        how="left",
    )


def test_dollar_values_sum_to_league_cap():
    """Season dollar values for all players must sum to base_cap × n_teams."""
    config = load_league_config()
    pts, proj, adp = _make_season_data()
    result = run_phase1_season(pts, proj, adp, config)

    season_values = _build_season_values_for_test(result, config)
    season_values, _ = compute_dollar_values(season_values, result["started_weekly"], config)

    total_cap = config["cap"]["base_cap"] * config["league"]["teams"]
    season_sum = season_values["dollar_value"].sum()
    assert math.isclose(season_sum, total_cap, rel_tol=1e-6), (
        f"Season dollar_value sum={season_sum:.4f} != total_league_cap={total_cap}"
    )


def test_weekly_dollar_values_sum_to_season():
    """Each player's weekly dollar_values must sum to their season dollar_value."""
    config = load_league_config()
    pts, proj, adp = _make_season_data()
    result = run_phase1_season(pts, proj, adp, config)

    season_values = _build_season_values_for_test(result, config)
    season_values, weekly_detail = compute_dollar_values(
        season_values, result["started_weekly"], config
    )

    weekly_sums = (
        weekly_detail.groupby(["season", "gsis_id"])["dollar_value"]
        .sum()
        .reset_index()
    )
    merged = season_values.merge(
        weekly_sums, on=["season", "gsis_id"], suffixes=("_season", "_weekly")
    )
    for _, row in merged.iterrows():
        assert math.isclose(
            row["dollar_value_season"], row["dollar_value_weekly"], rel_tol=1e-6, abs_tol=1e-9
        ), (
            f"{row['gsis_id']}: season DV={row['dollar_value_season']:.4f} "
            f"!= weekly sum={row['dollar_value_weekly']:.4f}"
        )
