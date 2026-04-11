from __future__ import annotations

import copy
import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.capture_model import PerfectCaptureModel, RationalCaptureModel
from src.valuation.phase1_assignment import assign_leaguewide_starting_set, compute_weekly_margins
from src.valuation.phase1_cutlines import compute_position_cutlines
from src.valuation.phase1_metrics import aggregate_sav
from src.valuation.phase1_realized import compute_rsv_ld_from_started_weekly
from src.valuation.roster_probability import compute_roster_probabilities


def _small_config() -> dict:
    config = copy.deepcopy(load_league_config())
    config["league"]["teams"] = 1
    config["lineup"] = {
        "qb": 1,
        "rb": 1,
        "wr": 1,
        "te": 1,
        "flex": 1,
        "superflex": 0,
    }
    config["roster"]["bench"] = 3
    config["roster"]["practice_squad_slots"] = 0
    config["capture_model"]["roster_model"]["active_roster_spots_per_team"] = 4
    config["capture_model"]["roster_model"]["kappa"] = 1.0
    config["capture_model"]["roster_model"]["gamma"] = 0.2
    config["capture_model"]["roster_model"]["stickiness_bonus"] = 0.0
    config["capture_model"]["practice_squad_model"]["enabled"] = False
    config["capture_model"]["tau_margin_scaling"] = 0.0
    return config


def _make_rho_proj_df() -> pd.DataFrame:
    players = [
        ("Cheap", "RB", 10.0),
        ("Expensive", "RB", 10.0),
        ("HighProj", "WR", 14.0),
        ("LowProj", "WR", 8.0),
        ("Fill1", "QB", 18.0),
        ("Fill2", "TE", 12.0),
        ("Fill3", "RB", 9.0),
        ("Fill4", "WR", 7.0),
    ]
    rows: list[dict] = []
    for week in [1, 2, 3]:
        for player, position, proj_points in players:
            rows.append(
                {
                    "season": 2024,
                    "week": week,
                    "gsis_id": f"G-{player}",
                    "player": player,
                    "position": position,
                    "proj_points": proj_points,
                }
            )
    return pd.DataFrame(rows)


def _make_rho_salary_df() -> pd.DataFrame:
    salaries = {
        "Cheap": 5.0,
        "Expensive": 25.0,
        "HighProj": 10.0,
        "LowProj": 10.0,
        "Fill1": 14.0,
        "Fill2": 11.0,
        "Fill3": 7.0,
        "Fill4": 6.0,
    }
    rows = []
    for player, market_salary in salaries.items():
        rows.append(
            {
                "season": 2024,
                "gsis_id": f"G-{player}",
                "player": player,
                "market_salary": market_salary,
            }
        )
    return pd.DataFrame(rows)


def _make_boom_scenario() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    proj_rows: list[dict] = []
    actual_rows: list[dict] = []

    def _add(player: str, position: str, proj: float, actual: float, rank: int) -> None:
        base = {
            "season": 2024,
            "week": 1,
            "gsis_id": f"G-{player}",
            "player": player,
            "position": position,
        }
        proj_rows.append({**base, "proj_points": proj})
        actual_rows.append({**base, "points": actual})
        adp_rows.append(
            {
                "season": 2024,
                "rank": rank,
                "gsis_id": f"G-{player}",
                "player": player,
                "position": position,
            }
        )

    adp_rows: list[dict] = []
    _add("QB1", "QB", proj=20.0, actual=20.0, rank=1)
    _add("QB2", "QB", proj=9.0, actual=0.0, rank=2)
    _add("RB1", "RB", proj=16.0, actual=20.0, rank=3)
    _add("WR1", "WR", proj=15.0, actual=15.0, rank=4)
    _add("WR2", "WR", proj=13.0, actual=0.0, rank=5)
    _add("TE1", "TE", proj=12.0, actual=12.0, rank=6)
    _add("RB3", "RB", proj=11.0, actual=0.0, rank=7)
    _add("WR3", "WR", proj=10.0, actual=0.0, rank=8)
    _add("BoomRB", "RB", proj=1.0, actual=18.0, rank=9)
    # RB4 provides a lower RB starter so BoomRB isn't the position cutline player.
    _add("RB4", "RB", proj=2.0, actual=5.0, rank=10)

    return pd.DataFrame(proj_rows), pd.DataFrame(actual_rows), pd.DataFrame(adp_rows)


def _build_started_weekly_df(actual_df: pd.DataFrame, config: dict) -> pd.DataFrame:
    pts_only = actual_df[["gsis_id", "player", "position", "points"]]
    started_df = assign_leaguewide_starting_set(pts_only, config)
    pos_cutlines = compute_position_cutlines(started_df)
    started = compute_weekly_margins(started_df, pos_cutlines)
    started["season"] = 2024
    started["week"] = 1
    return started


def test_rho_is_bounded():
    config = _small_config()
    rho_df = compute_roster_probabilities(_make_rho_proj_df(), _make_rho_salary_df(), config)

    assert rho_df["rho_active"].between(0.0, 1.0).all()
    assert rho_df["rho"].between(0.0, 1.0).all()


def test_rho_responds_to_desirability():
    config = _small_config()
    rho_df = compute_roster_probabilities(_make_rho_proj_df(), _make_rho_salary_df(), config)
    week1 = rho_df[rho_df["week"] == 1].set_index("player")

    assert week1.loc["Cheap", "rho"] > week1.loc["Expensive", "rho"]
    assert week1.loc["HighProj", "rho"] > week1.loc["LowProj", "rho"]


def test_capacity_enforcement_sanity():
    config = _small_config()
    capacity = config["league"]["teams"] * config["capture_model"]["roster_model"]["active_roster_spots_per_team"]
    rho_df = compute_roster_probabilities(_make_rho_proj_df(), _make_rho_salary_df(), config)

    week1_total = float(rho_df.loc[rho_df["week"] == 1, "rho_active"].sum())
    assert math.isclose(week1_total, capacity, abs_tol=0.05)


def test_rational_capture_reduces_boom_rb_rsv():
    config = _small_config()
    config["lineup"]["flex"] = 2
    config["lineup"]["superflex"] = 1
    config["capture_model"]["roster_model"]["active_roster_spots_per_team"] = 6

    proj_df, actual_df, adp_df = _make_boom_scenario()
    started_df = _build_started_weekly_df(actual_df, config)

    sav_df = aggregate_sav(started_df)
    boom_sav = sav_df.loc[sav_df["gsis_id"] == "G-BoomRB", "sav"].iloc[0]

    perfect_rsv_df = compute_rsv_ld_from_started_weekly(started_df, PerfectCaptureModel())
    boom_perfect = perfect_rsv_df.loc[perfect_rsv_df["gsis_id"] == "G-BoomRB", "rsv"].iloc[0]
    assert math.isclose(boom_perfect, boom_sav, rel_tol=1e-9)

    rational_model = RationalCaptureModel(proj_df=proj_df, adp_df=adp_df, config=config)
    rational_rsv_df = compute_rsv_ld_from_started_weekly(started_df, rational_model)
    boom_rational = rational_rsv_df.loc[rational_rsv_df["gsis_id"] == "G-BoomRB", "rsv"].iloc[0]

    assert boom_rational < boom_sav
    assert boom_rational < boom_perfect
