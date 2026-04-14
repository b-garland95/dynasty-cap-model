import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.phase1_assignment import (
    assign_leaguewide_starting_set,
    compute_full_pool_margins,
    compute_sav_for_week,
    compute_weekly_margins,
)
from src.valuation.phase1_cutlines import compute_position_cutlines, compute_weekly_raw_cutlines
from src.valuation.phase1_metrics import aggregate_sav


SLOT_COUNTS = {"QB": 10, "RB": 20, "WR": 30, "TE": 10, "FLEX": 20, "SF": 10}


def _make_assignment_week() -> pd.DataFrame:
    rows = []

    for i in range(1, 13):
        rows.append({"gsis_id": f"G-QB{i}", "player": f"QB{i}", "position": "QB", "points": 201 - i})

    for i in range(1, 31):
        rows.append({"gsis_id": f"G-RB{i}", "player": f"RB{i}", "position": "RB", "points": 151 - i})

    for i in range(1, 46):
        rows.append({"gsis_id": f"G-WR{i}", "player": f"WR{i}", "position": "WR", "points": 121 - i})

    for i in range(1, 19):
        rows.append({"gsis_id": f"G-TE{i}", "player": f"TE{i}", "position": "TE", "points": 81 - i})

    return pd.DataFrame(rows)



def _make_slot_gaming_week() -> pd.DataFrame:
    rows = []

    for i in range(1, 21):
        rows.append({"gsis_id": f"G-QB{i}", "player": f"QB{i}", "position": "QB", "points": 300 - i})

    rb_points = [240 - i for i in range(19)] + [200, 100]
    for i, points in enumerate(rb_points, start=1):
        rows.append({"gsis_id": f"G-RB{i}", "player": f"RB{i}", "position": "RB", "points": points})

    wr_points = [220 - i for i in range(30)] + [150 - i for i in range(20)]
    for i, points in enumerate(wr_points, start=1):
        rows.append({"gsis_id": f"G-WR{i}", "player": f"WR{i}", "position": "WR", "points": points})

    for i in range(1, 31):
        rows.append({"gsis_id": f"G-TE{i}", "player": f"TE{i}", "position": "TE", "points": 90 - i})

    return pd.DataFrame(rows)



def test_assign_leaguewide_starting_set_slot_counts_and_labels():
    config = load_league_config()
    week_df = _make_assignment_week()

    started_df = assign_leaguewide_starting_set(week_df, config)

    assert len(started_df) == sum(SLOT_COUNTS.values())
    assert started_df["assigned_slot"].value_counts().to_dict() == SLOT_COUNTS
    assert started_df["rank_within_slot"].min() == 1
    assert set(started_df.columns) == {"gsis_id", "player", "position", "points", "assigned_slot", "rank_within_slot"}



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

    started_df = assign_leaguewide_starting_set(week_df, config)
    pos_cutlines = compute_position_cutlines(started_df)
    margins_df = compute_weekly_margins(started_df, pos_cutlines)
    wrapper_df = compute_sav_for_week(week_df, pos_cutlines, config)

    assert margins_df.equals(wrapper_df)

    qb1 = margins_df.loc[margins_df["player"] == "QB1"].iloc[0]
    qb10 = margins_df.loc[margins_df["player"] == "QB10"].iloc[0]
    qb11 = margins_df.loc[margins_df["player"] == "QB11"].iloc[0]

    # All QBs are compared against the QB position cutline (QB12 = 189 pts),
    # regardless of whether they are in the QB or SF slot.
    assert qb1["assigned_slot"] == "QB"
    assert math.isclose(qb1["margin"], 11.0, rel_tol=1e-12)
    assert math.isclose(qb1["wmsv"], 11.0, rel_tol=1e-12)
    assert math.isclose(qb1["wdrag"], 0.0, rel_tol=1e-12)

    assert qb10["assigned_slot"] == "QB"
    assert math.isclose(qb10["margin"], 2.0, rel_tol=1e-12)
    assert math.isclose(qb10["wmsv"], 2.0, rel_tol=1e-12)
    assert math.isclose(qb10["wdrag"], 0.0, rel_tol=1e-12)

    # QB11 is in the SF slot but still compared against the QB position cutline.
    assert qb11["assigned_slot"] == "SF"
    assert math.isclose(qb11["margin"], 1.0, rel_tol=1e-12)
    assert math.isclose(qb11["wmsv"], 1.0, rel_tol=1e-12)
    assert math.isclose(qb11["wdrag"], 0.0, rel_tol=1e-12)

    # Negative margin: cutlines are now position-keyed.
    negative_df = compute_weekly_margins(
        pd.DataFrame(
            [{"player": "LowStarter", "position": "RB", "points": 8.0, "assigned_slot": "FLEX", "rank_within_slot": 1}]
        ),
        {"QB": 0.0, "RB": 10.0, "WR": 0.0, "TE": 0.0},
    )
    row = negative_df.iloc[0]
    assert math.isclose(row["margin"], -2.0, rel_tol=1e-12)
    assert math.isclose(row["wmsv"], 0.0, rel_tol=1e-12)
    assert math.isclose(row["wdrag"], -2.0, rel_tol=1e-12)



def test_position_cutline_eliminates_slot_gaming_artifact():
    """Position-based cutlines make the slot gaming artifact structurally impossible.

    Under the old slot-based approach, a player at the bottom of the RB slot
    could appear less valuable than a worse player who happened to land in
    the FLEX slot (with its lower cutline).  With position cutlines, all RBs
    are compared against the same RB position cutline regardless of slot.
    """
    config = load_league_config()
    week_df = _make_slot_gaming_week()

    started_df = assign_leaguewide_starting_set(week_df, config)
    pos_cutlines = compute_position_cutlines(started_df)
    margins_df = compute_sav_for_week(week_df, pos_cutlines, config)

    assert "RB21" not in margins_df["player"].tolist()

    rb20 = margins_df.loc[margins_df["player"] == "RB20"].iloc[0]
    assert rb20["assigned_slot"] == "RB"
    # RB20 is the position cutline player, so margin is 0.
    assert math.isclose(rb20["margin"], 0.0, rel_tol=1e-12)



def test_aggregate_sav_sums_wmsv_by_player():
    weekly_started = pd.DataFrame(
        [
            {"gsis_id": "G-A", "player": "A", "position": "RB", "points": 10.0, "wmsv": 1.5},
            {"gsis_id": "G-A", "player": "A", "position": "RB", "points": 20.0, "wmsv": 2.5},
            {"gsis_id": "G-B", "player": "B", "position": "WR", "points": 15.0, "wmsv": 0.0},
        ]
    )

    sav_df = aggregate_sav(weekly_started)

    player_a = sav_df.loc[sav_df["gsis_id"] == "G-A"].iloc[0]
    player_b = sav_df.loc[sav_df["gsis_id"] == "G-B"].iloc[0]

    assert math.isclose(player_a["sav"], 4.0, rel_tol=1e-12)
    assert math.isclose(player_a["total_points"], 30.0, rel_tol=1e-12)
    assert int(player_a["weeks_started_in_leaguewide_set"]) == 2
    assert player_a["player"] == "A"
    assert player_a["position"] == "RB"
    assert math.isclose(player_b["sav"], 0.0, rel_tol=1e-12)


def test_compute_full_pool_margins_keeps_active_low_scorers():
    config = load_league_config()
    week_df = _make_assignment_week()
    week_df["games_played"] = 1

    week_df = pd.concat(
        [
            week_df,
            pd.DataFrame(
                [
                    {
                        "gsis_id": "G-QB13",
                        "player": "QB13",
                        "position": "QB",
                        "points": 0.02,
                        "games_played": 1,
                    },
                    {
                        "gsis_id": "G-QB14",
                        "player": "QB14",
                        "position": "QB",
                        "points": 0.0,
                        "games_played": 0,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )

    started_df = assign_leaguewide_starting_set(week_df, config)
    pos_cutlines = compute_position_cutlines(started_df)
    full_pool = compute_full_pool_margins(week_df, pos_cutlines, config, min_points=0.1)

    assert "QB13" in full_pool["player"].values
    assert "QB14" not in full_pool["player"].values

    qb13 = full_pool.loc[full_pool["player"] == "QB13"].iloc[0]
    assert qb13["assigned_slot"] == "SF"
    assert qb13["rank_within_slot"] == 0
    assert math.isclose(qb13["points"], 0.02, rel_tol=1e-12)
