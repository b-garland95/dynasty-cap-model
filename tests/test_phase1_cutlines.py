import math

import pandas as pd
import pytest

from src.utils.config import load_league_config
from src.valuation.phase1_assignment import assign_leaguewide_starting_set
from src.valuation.phase1_cutlines import (
    POSITIONS,
    apply_shrinkage,
    compute_position_cutlines,
    compute_season_base_cutlines,
    compute_weekly_raw_cutlines,
)


def _make_synthetic_week() -> pd.DataFrame:
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


def _expected_cutlines_for_week(df: pd.DataFrame, config: dict) -> dict[str, float]:
    teams = config["league"]["teams"]
    lineup = config["lineup"]
    qb_req = teams * int(lineup["qb"])
    rb_req = teams * int(lineup["rb"])
    wr_req = teams * int(lineup["wr"])
    te_req = teams * int(lineup["te"])
    flex_req = teams * int(lineup["flex"])
    sf_req = teams * int(lineup["superflex"])

    remaining = df.copy()

    def take_top(pos_list: list[str], n: int) -> float:
        nonlocal remaining
        elig = remaining[remaining["position"].isin(pos_list)].sort_values("points", ascending=False)
        if len(elig) < n:
            raise ValueError("Insufficient eligible players")
        chosen = elig.head(n)
        cut = float(chosen["points"].iloc[-1])
        remaining = remaining.drop(index=chosen.index)
        return cut

    exp = {}
    exp["QB"] = take_top(["QB"], qb_req)
    exp["RB"] = take_top(["RB"], rb_req)
    exp["WR"] = take_top(["WR"], wr_req)
    exp["TE"] = take_top(["TE"], te_req)
    exp["FLEX"] = take_top(["RB", "WR", "TE"], flex_req)
    exp["SF"] = take_top(["QB", "RB", "WR", "TE"], sf_req)
    return exp


def test_compute_weekly_raw_cutlines_matches_expected():
    config = load_league_config()
    week_df = _make_synthetic_week()

    raw = compute_weekly_raw_cutlines(week_df, config)
    exp = _expected_cutlines_for_week(week_df, config)

    assert set(raw.keys()) == {"QB", "RB", "WR", "TE", "FLEX", "SF"}

    for key in raw:
        assert math.isclose(raw[key], exp[key], rel_tol=0.0, abs_tol=0.0)


def test_flex_and_sf_use_remaining_pool_after_required_slots():
    config = load_league_config()
    week_df = _make_synthetic_week()

    raw = compute_weekly_raw_cutlines(week_df, config)

    assert raw["RB"] > raw["FLEX"]
    assert raw["WR"] > raw["FLEX"]
    assert raw["QB"] > raw["SF"]
    assert raw["FLEX"] > raw["SF"]


def test_shrinkage_math_is_correct_for_one_slot():
    config = load_league_config()
    raw = {"QB": 10.0, "RB": 20.0, "WR": 30.0, "TE": 40.0, "FLEX": 50.0, "SF": 60.0}
    base = {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0, "FLEX": 0.0, "SF": 0.0}

    shrunk = apply_shrinkage(raw, base, config)

    lam_qb = float(config["valuation"]["shrinkage_lambdas"]["QB"])
    expected_qb = lam_qb * 0.0 + (1.0 - lam_qb) * 10.0
    assert math.isclose(shrunk["QB"], expected_qb, rel_tol=1e-12)


def test_compute_season_base_cutlines_uses_median():
    raw_by_week = [
        {"QB": 10, "RB": 1, "WR": 5, "TE": 9, "FLEX": 7, "SF": 3},
        {"QB": 20, "RB": 2, "WR": 6, "TE": 8, "FLEX": 6, "SF": 4},
        {"QB": 30, "RB": 3, "WR": 7, "TE": 7, "FLEX": 5, "SF": 5},
    ]
    base = compute_season_base_cutlines(raw_by_week)
    assert base["QB"] == 20
    assert base["RB"] == 2
    assert base["WR"] == 6
    assert base["TE"] == 8
    assert base["FLEX"] == 6
    assert base["SF"] == 4


def test_insufficient_pool_raises_value_error():
    config = load_league_config()
    rows = [{"gsis_id": f"G-QB{i}", "player": f"QB{i}", "position": "QB", "points": 50 - i} for i in range(1, 10)]
    rows += [{"gsis_id": f"G-RB{i}", "player": f"RB{i}", "position": "RB", "points": 100 - i} for i in range(1, 31)]
    rows += [{"gsis_id": f"G-WR{i}", "player": f"WR{i}", "position": "WR", "points": 90 - i} for i in range(1, 46)]
    rows += [{"gsis_id": f"G-TE{i}", "player": f"TE{i}", "position": "TE", "points": 80 - i} for i in range(1, 19)]
    week_df = pd.DataFrame(rows)

    with pytest.raises(ValueError, match="Insufficient eligible players for slot QB"):
        compute_weekly_raw_cutlines(week_df, config)


def test_compute_position_cutlines():
    """Position cutline = min points of any starter of that position across all slots."""
    config = load_league_config()
    week_df = _make_synthetic_week()
    started_df = assign_leaguewide_starting_set(week_df, config)

    pos_cl = compute_position_cutlines(started_df)

    assert set(pos_cl.keys()) == {"QB", "RB", "WR", "TE"}
    # QB: 12 QBs available, 10 fill QB slot, 2 fill SF → QB12 (189 pts) is lowest QB starter.
    assert math.isclose(pos_cl["QB"], 189.0)
    # RB: 30 RBs, 20 fill RB slot, remaining fill FLEX → lowest RB starter in any slot.
    # RB21-RB30 have points 130..121. The FLEX slots (20 total) take the best remaining
    # RB/WR/TE. RB21=130, RB22=129, ... compete with WR31=90, WR32=89, ... and TE11=70, ...
    # The top 20 remaining are RB21-30 (130-121) + WR31-40 (90-81). RB30=121 is in FLEX.
    assert math.isclose(pos_cl["RB"], 121.0)
    # WR: 30 fill WR slot, WR31-40 in FLEX, WR41-45 in SF. WR45=76 is lowest WR starter.
    assert math.isclose(pos_cl["WR"], 76.0)
    # TE: 10 fill TE slot, TE11-13 fill SF. TE13=68 is lowest TE starter.
    assert math.isclose(pos_cl["TE"], 68.0)


def test_compute_season_base_cutlines_with_position_keys():
    raw_by_week = [
        {"QB": 20.0, "RB": 10.0, "WR": 8.0, "TE": 5.0},
        {"QB": 22.0, "RB": 12.0, "WR": 9.0, "TE": 6.0},
        {"QB": 24.0, "RB": 14.0, "WR": 7.0, "TE": 4.0},
    ]
    base = compute_season_base_cutlines(raw_by_week, keys=POSITIONS)
    assert base["QB"] == 22.0
    assert base["RB"] == 12.0
    assert base["WR"] == 8.0
    assert base["TE"] == 5.0


def test_apply_shrinkage_with_position_keys():
    config = load_league_config()
    raw = {"QB": 20.0, "RB": 10.0, "WR": 8.0, "TE": 5.0}
    base = {"QB": 22.0, "RB": 12.0, "WR": 9.0, "TE": 6.0}

    shrunk = apply_shrinkage(raw, base, config, keys=POSITIONS)

    lam_qb = float(config["valuation"]["shrinkage_lambdas"]["QB"])
    expected_qb = lam_qb * 22.0 + (1.0 - lam_qb) * 20.0
    assert math.isclose(shrunk["QB"], expected_qb, rel_tol=1e-12)
