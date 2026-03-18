import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.phase1_assignment import (
    assign_leaguewide_starting_set,
    compute_sav_for_week,
    compute_weekly_margins,
)
from src.valuation.phase1_cutlines import compute_weekly_raw_cutlines
from src.valuation.phase1_metrics import aggregate_sav


SLOT_COUNTS = {"QB": 10, "RB": 20, "WR": 30, "TE": 10, "FLEX": 20, "SF": 10}


def _make_assignment_week() -> pd.DataFrame:
    rows = []

    for i in range(1, 13):
        rows.append({"player": f"QB{i}", "position": "QB", "points": 201 - i})

    for i in range(1, 31):
        rows.append({"player": f"RB{i}", "position": "RB", "points": 151 - i})

    for i in range(1, 46):
        rows.append({"player": f"WR{i}", "position": "WR", "points": 121 - i})

    for i in range(1, 19):
        rows.append({"player": f"TE{i}", "position": "TE", "points": 81 - i})

    return pd.DataFrame(rows)



def _make_slot_gaming_week() -> pd.DataFrame:
    rows = []

    for i in range(1, 21):
        rows.append({"player": f"QB{i}", "position": "QB", "points": 300 - i})

    rb_points = [240 - i for i in range(19)] + [200, 100]
    for i, points in enumerate(rb_points, start=1):
        rows.append({"player": f"RB{i}", "position": "RB", "points": points})

    wr_points = [220 - i for i in range(30)] + [150 - i for i in range(20)]
    for i, points in enumerate(wr_points, start=1):
        rows.append({"player": f"WR{i}", "position": "WR", "points": points})

    for i in range(1, 31):
        rows.append({"player": f"TE{i}", "position": "TE", "points": 90 - i})

    return pd.DataFrame(rows)



def test_assign_leaguewide_starting_set_slot_counts_and_labels():
    config = load_league_config()
    week_df = _make_assignment_week()

    started_df = assign_leaguewide_starting_set(week_df, config)

    assert len(started_df) == sum(SLOT_COUNTS.values())
    assert started_df["assigned_slot"].value_counts().to_dict() == SLOT_COUNTS
    assert started_df["rank_within_slot"].min() == 1
    assert set(started_df.columns) == {"player", "position", "points", "assigned_slot", "rank_within_slot"}



def test_flex_and_sf_are_selected_from_remaining_pools():
    config = load_league_config()
    week_df = _make_assignment_week()

    started_df = assign_leaguewide_starting_set(week_df, config)

    flex_players = started_df.loc[started_df["assigned_slot"] == "FLEX", "player"].tolist()
    sf_players = started_df.loc[started_df["assigned_slot"] == "SF", "player"].tolist()

    assert "RB21" in flex_players
    assert "RB30" in flex_players
    assert "WR31" in flex_players
    assert "WR40" in flex_players
    assert "QB11" in sf_players
    assert "QB12" in sf_players
    assert len(sf_players) == 10



def test_compute_weekly_margins_and_wrapper():
    config = load_league_config()
    week_df = _make_assignment_week()
    cutlines = compute_weekly_raw_cutlines(week_df, config)

    started_df = assign_leaguewide_starting_set(week_df, config)
    margins_df = compute_weekly_margins(started_df, cutlines)
    wrapper_df = compute_sav_for_week(week_df, cutlines, config)

    assert margins_df.equals(wrapper_df)

    qb1 = margins_df.loc[margins_df["player"] == "QB1"].iloc[0]
    qb10 = margins_df.loc[margins_df["player"] == "QB10"].iloc[0]
    qb11 = margins_df.loc[margins_df["player"] == "QB11"].iloc[0]

    assert qb1["assigned_slot"] == "QB"
    assert math.isclose(qb1["margin"], 9.0, rel_tol=1e-12)
    assert math.isclose(qb1["wmsv"], 9.0, rel_tol=1e-12)
    assert math.isclose(qb1["wdrag"], 0.0, rel_tol=1e-12)

    assert qb10["assigned_slot"] == "QB"
    assert math.isclose(qb10["margin"], 0.0, rel_tol=1e-12)
    assert math.isclose(qb10["wmsv"], 0.0, rel_tol=1e-12)
    assert math.isclose(qb10["wdrag"], 0.0, rel_tol=1e-12)

    assert qb11["assigned_slot"] == "SF"
    expected_qb11_margin = float(qb11["points"]) - float(cutlines["SF"])
    assert math.isclose(qb11["margin"], expected_qb11_margin, rel_tol=1e-12)
    assert math.isclose(qb11["wmsv"], expected_qb11_margin, rel_tol=1e-12)
    assert math.isclose(qb11["wdrag"], 0.0, rel_tol=1e-12)

    negative_df = compute_weekly_margins(
        pd.DataFrame(
            [{"player": "LowStarter", "position": "RB", "points": 8.0, "assigned_slot": "FLEX", "rank_within_slot": 1}]
        ),
        {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0, "FLEX": 10.0, "SF": 0.0},
    )
    row = negative_df.iloc[0]
    assert math.isclose(row["margin"], -2.0, rel_tol=1e-12)
    assert math.isclose(row["wmsv"], 0.0, rel_tol=1e-12)
    assert math.isclose(row["wdrag"], -2.0, rel_tol=1e-12)



def test_slot_gaming_artifact_is_prevented():
    config = load_league_config()
    week_df = _make_slot_gaming_week()
    cutlines = compute_weekly_raw_cutlines(week_df, config)

    started_df = compute_sav_for_week(week_df, cutlines, config)

    assert "RB21" not in started_df["player"].tolist()

    rb20 = started_df.loc[started_df["player"] == "RB20"].iloc[0]
    assert rb20["assigned_slot"] == "RB"
    assert cutlines["FLEX"] < cutlines["RB"]
    assert float(rb20["points"]) > cutlines["FLEX"]
    assert math.isclose(rb20["margin"], 0.0, rel_tol=1e-12)



def test_aggregate_sav_sums_wmsv_by_player():
    weekly_started = pd.DataFrame(
        [
            {"player": "A", "points": 10.0, "wmsv": 1.5},
            {"player": "A", "points": 20.0, "wmsv": 2.5},
            {"player": "B", "points": 15.0, "wmsv": 0.0},
        ]
    )

    sav_df = aggregate_sav(weekly_started)

    player_a = sav_df.loc[sav_df["player"] == "A"].iloc[0]
    player_b = sav_df.loc[sav_df["player"] == "B"].iloc[0]

    assert math.isclose(player_a["sav"], 4.0, rel_tol=1e-12)
    assert math.isclose(player_a["total_points"], 30.0, rel_tol=1e-12)
    assert int(player_a["weeks_started_in_leaguewide_set"]) == 2
    assert math.isclose(player_b["sav"], 0.0, rel_tol=1e-12)
