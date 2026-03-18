import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.capture_model import PerfectCaptureModel
from src.valuation.phase1_metrics import aggregate_sav
from src.valuation.phase1_par import compute_par_by_player, compute_position_replacement_level_par
from src.valuation.phase1_realized import (
    compute_capture_gap,
    compute_rsv_ld_from_started_weekly,
    compute_rsv_ld_weekly,
)
from src.valuation.phase1_splits import (
    add_season_phase,
    aggregate_par_splits,
    aggregate_rsv_ld_splits,
    aggregate_sav_splits,
    compute_capture_gap_splits,
)



def _make_par_points_df() -> pd.DataFrame:
    rows = []
    for week in [14, 15]:
        for i in range(1, 11):
            rows.append({"season": 2024, "week": week, "player": f"QB{i}_w{week}", "position": "QB", "points": 30 - i - (week - 14)})
        for i in range(1, 21):
            rows.append({"season": 2024, "week": week, "player": f"RB{i}_w{week}", "position": "RB", "points": 40 - i - (week - 14)})
        for i in range(1, 31):
            rows.append({"season": 2024, "week": week, "player": f"WR{i}_w{week}", "position": "WR", "points": 50 - i - (week - 14)})
        for i in range(1, 11):
            rows.append({"season": 2024, "week": week, "player": f"TE{i}_w{week}", "position": "TE", "points": 20 - i - (week - 14)})
    return pd.DataFrame(rows)



def _make_started_weekly_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"season": 2024, "week": 14, "player": "A", "position": "RB", "points": 20.0, "wmsv": 5.0, "wdrag": 0.0},
            {"season": 2024, "week": 15, "player": "A", "position": "RB", "points": 18.0, "wmsv": 3.0, "wdrag": -1.0},
            {"season": 2024, "week": 14, "player": "B", "position": "WR", "points": 12.0, "wmsv": 0.0, "wdrag": -2.0},
            {"season": 2024, "week": 15, "player": "B", "position": "WR", "points": 16.0, "wmsv": 4.0, "wdrag": 0.0},
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
            {"season": 2024, "week": 14, "player": "A", "position": "QB", "points": 12.0},
            {"season": 2024, "week": 15, "player": "A", "position": "QB", "points": 8.0},
            {"season": 2024, "week": 14, "player": "B", "position": "RB", "points": 7.0},
        ]
    )
    r_par = {"QB": 10.0, "RB": 9.0, "WR": 0.0, "TE": 0.0}

    par_df = compute_par_by_player(season_points_df, r_par)
    player_a = par_df.loc[par_df["player"] == "A"].iloc[0]
    player_b = par_df.loc[par_df["player"] == "B"].iloc[0]

    assert math.isclose(player_a["par"], 0.0, rel_tol=1e-12)
    assert math.isclose(player_b["par"], -2.0, rel_tol=1e-12)



def test_perfect_capture_model_yields_rsv_equal_sav_and_ld_equal_wdrag_sum():
    started_weekly_df = _make_started_weekly_df()

    sav_df = aggregate_sav(started_weekly_df)
    realized_df = compute_rsv_ld_from_started_weekly(started_weekly_df, PerfectCaptureModel())

    merged = sav_df.merge(realized_df, on=["season", "player"])
    assert merged["sav"].tolist() == merged["rsv"].tolist()

    player_a = merged.loc[merged["player"] == "A"].iloc[0]
    player_b = merged.loc[merged["player"] == "B"].iloc[0]
    assert math.isclose(player_a["ld"], -1.0, rel_tol=1e-12)
    assert math.isclose(player_b["ld"], -2.0, rel_tol=1e-12)



def test_compute_capture_gap_is_zero_under_perfect_capture():
    started_weekly_df = _make_started_weekly_df()
    sav_df = aggregate_sav(started_weekly_df)
    rsv_df = compute_rsv_ld_from_started_weekly(started_weekly_df, PerfectCaptureModel())

    cg_df = compute_capture_gap(sav_df, rsv_df)

    assert cg_df["cg"].tolist() == [0.0, 0.0]



def test_add_season_phase_and_split_aggregations_work():
    config = load_league_config()
    started_weekly_df = _make_started_weekly_df()
    realized_weekly_df = compute_rsv_ld_weekly(started_weekly_df, PerfectCaptureModel())

    phased = add_season_phase(started_weekly_df, config)
    assert phased.loc[phased["week"] == 14, "phase"].eq("regular").all()
    assert phased.loc[phased["week"] == 15, "phase"].eq("playoffs").all()

    sav_splits = aggregate_sav_splits(started_weekly_df, config)
    rsv_ld_splits = aggregate_rsv_ld_splits(realized_weekly_df, config)
    cg_splits = compute_capture_gap_splits(sav_splits, rsv_ld_splits[["season", "player", "phase", "rsv"]])

    a_regular = sav_splits.loc[(sav_splits["player"] == "A") & (sav_splits["phase"] == "regular")].iloc[0]
    a_playoffs = rsv_ld_splits.loc[(rsv_ld_splits["player"] == "A") & (rsv_ld_splits["phase"] == "playoffs")].iloc[0]
    b_regular = rsv_ld_splits.loc[(rsv_ld_splits["player"] == "B") & (rsv_ld_splits["phase"] == "regular")].iloc[0]

    assert math.isclose(a_regular["sav"], 5.0, rel_tol=1e-12)
    assert math.isclose(a_playoffs["rsv"], 3.0, rel_tol=1e-12)
    assert math.isclose(a_playoffs["ld"], -1.0, rel_tol=1e-12)
    assert math.isclose(b_regular["ld"], -2.0, rel_tol=1e-12)
    assert cg_splits["cg"].eq(0.0).all()



def test_aggregate_par_splits_sums_by_phase():
    config = load_league_config()
    par_weekly_df = pd.DataFrame(
        [
            {"season": 2024, "week": 14, "player": "A", "par_week": 2.0},
            {"season": 2024, "week": 15, "player": "A", "par_week": -1.0},
            {"season": 2024, "week": 15, "player": "B", "par_week": 3.0},
        ]
    )

    par_splits = aggregate_par_splits(par_weekly_df, config)

    a_regular = par_splits.loc[(par_splits["player"] == "A") & (par_splits["phase"] == "regular")].iloc[0]
    a_playoffs = par_splits.loc[(par_splits["player"] == "A") & (par_splits["phase"] == "playoffs")].iloc[0]
    b_playoffs = par_splits.loc[(par_splits["player"] == "B") & (par_splits["phase"] == "playoffs")].iloc[0]

    assert math.isclose(a_regular["par"], 2.0, rel_tol=1e-12)
    assert math.isclose(a_playoffs["par"], -1.0, rel_tol=1e-12)
    assert math.isclose(b_playoffs["par"], 3.0, rel_tol=1e-12)
