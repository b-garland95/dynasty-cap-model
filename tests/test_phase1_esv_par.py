import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.capture_model import PerfectCaptureModel
from src.valuation.phase1_metrics import aggregate_sav
from src.valuation.phase1_par import compute_par_by_player, compute_position_replacement_level_par
from src.valuation.phase1_esv import (
    compute_capture_gap,
    compute_esv_ld_from_started_weekly,
    compute_esv_ld_weekly,
)
from src.valuation.phase1_splits import (
    add_season_phase,
    aggregate_par_splits,
    aggregate_esv_ld_splits,
    aggregate_sav_splits,
    compute_capture_gap_splits,
)



def _make_par_points_df() -> pd.DataFrame:
    rows = []
    for week in [14, 15]:
        for i in range(1, 11):
            rows.append({"season": 2024, "week": week, "gsis_id": f"G-QB{i}_w{week}", "player": f"QB{i}_w{week}", "position": "QB", "points": 30 - i - (week - 14)})
        for i in range(1, 21):
            rows.append({"season": 2024, "week": week, "gsis_id": f"G-RB{i}_w{week}", "player": f"RB{i}_w{week}", "position": "RB", "points": 40 - i - (week - 14)})
        for i in range(1, 31):
            rows.append({"season": 2024, "week": week, "gsis_id": f"G-WR{i}_w{week}", "player": f"WR{i}_w{week}", "position": "WR", "points": 50 - i - (week - 14)})
        for i in range(1, 11):
            rows.append({"season": 2024, "week": week, "gsis_id": f"G-TE{i}_w{week}", "player": f"TE{i}_w{week}", "position": "TE", "points": 20 - i - (week - 14)})
    return pd.DataFrame(rows)



def _make_started_weekly_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"season": 2024, "week": 14, "gsis_id": "G-A", "player": "A", "position": "RB", "points": 20.0, "margin": 5.0, "wmsv": 5.0, "wdrag": 0.0},
            {"season": 2024, "week": 15, "gsis_id": "G-A", "player": "A", "position": "RB", "points": 18.0, "margin": 2.0, "wmsv": 3.0, "wdrag": -1.0},
            {"season": 2024, "week": 14, "gsis_id": "G-B", "player": "B", "position": "WR", "points": 12.0, "margin": -2.0, "wmsv": 0.0, "wdrag": -2.0},
            {"season": 2024, "week": 15, "gsis_id": "G-B", "player": "B", "position": "WR", "points": 16.0, "margin": 4.0, "wmsv": 4.0, "wdrag": 0.0},
        ]
    )



def test_compute_position_replacement_level_par_uses_median_weekly_nth():
    config = load_league_config()
    season_points_df = _make_par_points_df()

    replacement = compute_position_replacement_level_par(season_points_df, config)

    assert replacement == {"QB": 19.5, "RB": 19.5, "WR": 19.5, "TE": 9.5}



def test_compute_par_by_player_aggregates_without_clamping():
    season_points_df = pd.DataFrame(
        [
            {"season": 2024, "week": 14, "gsis_id": "G-A", "player": "A", "position": "QB", "points": 12.0},
            {"season": 2024, "week": 15, "gsis_id": "G-A", "player": "A", "position": "QB", "points": 8.0},
            {"season": 2024, "week": 14, "gsis_id": "G-B", "player": "B", "position": "RB", "points": 7.0},
        ]
    )
    r_par = {"QB": 10.0, "RB": 9.0, "WR": 0.0, "TE": 0.0}

    par_df = compute_par_by_player(season_points_df, r_par)
    player_a = par_df.loc[par_df["gsis_id"] == "G-A"].iloc[0]
    player_b = par_df.loc[par_df["gsis_id"] == "G-B"].iloc[0]

    assert math.isclose(player_a["par"], 0.0, rel_tol=1e-12)
    assert math.isclose(player_b["par"], -2.0, rel_tol=1e-12)



def test_perfect_capture_model_yields_esv_equal_total_margin_and_ld_equal_wdrag_sum():
    """Under PerfectCaptureModel (σ=1), ESV = sum(margin) = SAV + LD.

    ESV now weights full margin (positive and negative) by start_prob.
    Under perfect capture, this means ESV = SAV + LD (total net margin).
    """
    started_weekly_df = _make_started_weekly_df()

    sav_df = aggregate_sav(started_weekly_df)
    realized_df = compute_esv_ld_from_started_weekly(started_weekly_df, PerfectCaptureModel())

    merged = sav_df.merge(realized_df, on=["season", "gsis_id"])

    # ESV = SAV + LD (sum of full margin, not just positive)
    for _, row in merged.iterrows():
        assert math.isclose(row["esv"], row["sav"] + row["ld"], rel_tol=1e-12), (
            f"{row['gsis_id']}: ESV={row['esv']:.4f} != SAV+LD={row['sav'] + row['ld']:.4f}"
        )

    player_a = merged.loc[merged["gsis_id"] == "G-A"].iloc[0]
    player_b = merged.loc[merged["gsis_id"] == "G-B"].iloc[0]
    assert math.isclose(player_a["esv"], 7.0, rel_tol=1e-12)  # margin: 5.0 + 2.0
    assert math.isclose(player_b["esv"], 2.0, rel_tol=1e-12)  # margin: -2.0 + 4.0
    assert math.isclose(player_a["ld"], -1.0, rel_tol=1e-12)
    assert math.isclose(player_b["ld"], -2.0, rel_tol=1e-12)



def test_compute_capture_gap_equals_negative_ld_under_perfect_capture():
    """Under PerfectCaptureModel, CG = SAV - ESV = SAV - (SAV + LD) = -LD."""
    started_weekly_df = _make_started_weekly_df()
    sav_df = aggregate_sav(started_weekly_df)
    esv_df = compute_esv_ld_from_started_weekly(started_weekly_df, PerfectCaptureModel())

    cg_df = compute_capture_gap(sav_df, esv_df)

    for _, row in cg_df.iterrows():
        assert math.isclose(row["cg"], -row["ld"], rel_tol=1e-12), (
            f"{row['gsis_id']}: CG={row['cg']:.4f} != -LD={-row['ld']:.4f}"
        )



def test_add_season_phase_and_split_aggregations_work():
    config = load_league_config()
    started_weekly_df = _make_started_weekly_df()
    esv_weekly_df = compute_esv_ld_weekly(started_weekly_df, PerfectCaptureModel())

    phased = add_season_phase(started_weekly_df, config)
    assert phased.loc[phased["week"] == 14, "phase"].eq("regular").all()
    assert phased.loc[phased["week"] == 15, "phase"].eq("playoffs").all()

    sav_splits = aggregate_sav_splits(started_weekly_df, config)
    esv_ld_splits = aggregate_esv_ld_splits(esv_weekly_df, config)
    cg_splits = compute_capture_gap_splits(sav_splits, esv_ld_splits[["season", "gsis_id", "phase", "esv"]])

    a_regular = sav_splits.loc[(sav_splits["gsis_id"] == "G-A") & (sav_splits["phase"] == "regular")].iloc[0]
    a_playoffs = esv_ld_splits.loc[(esv_ld_splits["gsis_id"] == "G-A") & (esv_ld_splits["phase"] == "playoffs")].iloc[0]
    b_regular = esv_ld_splits.loc[(esv_ld_splits["gsis_id"] == "G-B") & (esv_ld_splits["phase"] == "regular")].iloc[0]

    assert math.isclose(a_regular["sav"], 5.0, rel_tol=1e-12)
    assert math.isclose(a_playoffs["esv"], 2.0, rel_tol=1e-12)  # margin=2.0 (wmsv=3 + wdrag=-1)
    assert math.isclose(a_playoffs["ld"], -1.0, rel_tol=1e-12)
    assert math.isclose(b_regular["ld"], -2.0, rel_tol=1e-12)



def test_aggregate_par_splits_sums_by_phase():
    config = load_league_config()
    par_weekly_df = pd.DataFrame(
        [
            {"season": 2024, "week": 14, "gsis_id": "G-A", "player": "A", "par_week": 2.0},
            {"season": 2024, "week": 15, "gsis_id": "G-A", "player": "A", "par_week": -1.0},
            {"season": 2024, "week": 15, "gsis_id": "G-B", "player": "B", "par_week": 3.0},
        ]
    )

    par_splits = aggregate_par_splits(par_weekly_df, config)

    a_regular = par_splits.loc[(par_splits["gsis_id"] == "G-A") & (par_splits["phase"] == "regular")].iloc[0]
    a_playoffs = par_splits.loc[(par_splits["gsis_id"] == "G-A") & (par_splits["phase"] == "playoffs")].iloc[0]
    b_playoffs = par_splits.loc[(par_splits["gsis_id"] == "G-B") & (par_splits["phase"] == "playoffs")].iloc[0]

    assert math.isclose(a_regular["par"], 2.0, rel_tol=1e-12)
    assert math.isclose(a_playoffs["par"], -1.0, rel_tol=1e-12)
    assert math.isclose(b_playoffs["par"], 3.0, rel_tol=1e-12)
