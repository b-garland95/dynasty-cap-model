import math

import pandas as pd
import pytest

from src.contracts.free_agent_market import (
    build_free_agent_market_table,
    compute_cap_environment,
)
from src.utils.config import load_league_config


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _config():
    return load_league_config()


def _tv_df():
    return pd.DataFrame([
        {"player": "Free Agent A", "position": "WR", "team": "KC",  "tv_y0": 20.0, "adp": 5.0,  "is_rostered": False, "esv_p25": 15.0, "esv_p50": 20.0, "esv_p75": 25.0},
        {"player": "Free Agent B", "position": "RB", "team": "DAL", "tv_y0": 12.0, "adp": 12.0, "is_rostered": False, "esv_p25":  8.0, "esv_p50": 12.0, "esv_p75": 16.0},
        {"player": "Rostered C",   "position": "QB", "team": "Team Alpha", "tv_y0": 30.0, "adp": 2.0,  "is_rostered": True,  "esv_p25": 22.0, "esv_p50": 30.0, "esv_p75": 38.0},
    ])


def _cap_health_df(cap_usage_per_team: float = 200.0, n_teams: int = 2):
    return pd.DataFrame([
        {"team": f"Team {i}", "current_cap_usage": cap_usage_per_team}
        for i in range(n_teams)
    ])


def _mini_config(base_cap: float = 300.0, n_teams: int = 2, alpha: float = 0.5) -> dict:
    cfg = _config()
    cfg["cap"]["base_cap"] = base_cap
    cfg["league"]["teams"] = n_teams
    cfg["free_agent_market"] = {"cap_pressure_alpha": alpha}
    return cfg


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_free_agent_filter_excludes_rostered():
    tv = _tv_df()
    cfg = _mini_config()
    cap_h = _cap_health_df()

    player_df, _ = build_free_agent_market_table(tv, cap_h, cfg)

    assert "Rostered C" not in set(player_df["player"])
    assert {"Free Agent A", "Free Agent B"} == set(player_df["player"])


def test_include_rostered_includes_all():
    tv = _tv_df()
    cfg = _mini_config()
    cap_h = _cap_health_df()

    player_df, _ = build_free_agent_market_table(tv, cap_h, cfg, include_rostered=True)

    assert set(player_df["player"]) == {"Free Agent A", "Free Agent B", "Rostered C"}


def test_market_multiplier_cap_surplus():
    # 2 teams × $300 cap = $600 total; each team uses $100 → $200 cap remaining
    # FA value = 20 + 12 = $32 → CVR = 200 / 32 ≈ 6.25 → multiplier = 6.25^0.5 ≈ 2.5
    tv = _tv_df()
    cfg = _mini_config(base_cap=300.0, n_teams=2, alpha=0.5)
    cap_h = _cap_health_df(cap_usage_per_team=100.0, n_teams=2)

    env = compute_cap_environment(tv, cap_h, cfg)

    assert env["cap_to_value_ratio"] > 1.0
    assert env["market_multiplier"] > 1.0
    assert env["inflation_pct"] > 0.0


def test_market_multiplier_cap_deficit():
    # 2 teams × $300 cap = $600; each team uses $298 → $4 cap remaining
    # FA value = 20 + 12 = $32 → CVR = 4 / 32 = 0.125 → multiplier < 1
    tv = _tv_df()
    cfg = _mini_config(base_cap=300.0, n_teams=2, alpha=0.5)
    cap_h = _cap_health_df(cap_usage_per_team=298.0, n_teams=2)

    env = compute_cap_environment(tv, cap_h, cfg)

    assert env["cap_to_value_ratio"] < 1.0
    assert env["market_multiplier"] < 1.0
    assert env["inflation_pct"] < 0.0


def test_market_adjusted_value_applies_multiplier():
    # 2 teams × ($300 - $100) = $400 cap; FA value = 32 → CVR = 12.5 → multiplier = sqrt(12.5)
    # market_adjusted_value should equal projected_value × multiplier for each player
    tv = _tv_df()
    cfg = _mini_config(base_cap=300.0, n_teams=2, alpha=0.5)
    cap_h = _cap_health_df(cap_usage_per_team=100.0, n_teams=2)

    player_df, env = build_free_agent_market_table(tv, cap_h, cfg)

    multiplier = env["market_multiplier"]
    assert multiplier != 1.0  # ensure we're actually testing non-trivial adjustment
    for _, row in player_df.iterrows():
        expected = row["projected_value"] * multiplier
        assert math.isclose(row["market_adjusted_value"], expected, rel_tol=1e-9)
    assert all(player_df["market_premium_pct"] == env["inflation_pct"])


def test_negative_tv_excluded_from_total_fa_value():
    # Negative TV players are long-tail non-picks; they must not reduce total_fa_value.
    tv = pd.DataFrame([
        {"player": "Good FA",  "position": "WR", "team": "KC",  "tv_y0":  20.0, "is_rostered": False},
        {"player": "Bad FA",   "position": "RB", "team": "DAL", "tv_y0":  -5.0, "is_rostered": False},
        {"player": "Rostered", "position": "QB", "team": "NE",  "tv_y0":  30.0, "is_rostered": True},
    ])
    cfg = _mini_config()
    cap_h = _cap_health_df()

    env = compute_cap_environment(tv, cap_h, cfg)

    # Only the positive FA value (20.0) should count; -5.0 and 30.0 (rostered) excluded
    assert math.isclose(env["total_fa_value"], 20.0, rel_tol=1e-9)


def test_zero_fa_value_returns_neutral_multiplier():
    # All players rostered → no FA value → CVR defaults to 1.0 → multiplier = 1.0
    tv = pd.DataFrame([
        {"player": "Rostered X", "position": "QB", "team": "Team A", "tv_y0": 25.0, "is_rostered": True},
    ])
    cfg = _mini_config()
    cap_h = _cap_health_df()

    env = compute_cap_environment(tv, cap_h, cfg)

    assert math.isclose(env["cap_to_value_ratio"], 1.0)
    assert math.isclose(env["market_multiplier"], 1.0)


def test_team_adjustments_reduce_available_cap():
    # Without adjustments: 2 teams × ($300 - $100) = $400 available
    # With dead_money=50 per team: 2 × ($300 - $100 - $50) = $300 available
    tv = _tv_df()
    cfg = _mini_config(base_cap=300.0, n_teams=2, alpha=0.5)
    cap_h = pd.DataFrame([
        {"team": "Team 0", "current_cap_usage": 100.0},
        {"team": "Team 1", "current_cap_usage": 100.0},
    ])

    env_no_adj = compute_cap_environment(tv, cap_h, cfg)
    env_with_adj = compute_cap_environment(
        tv, cap_h, cfg,
        team_adjustments={
            "Team 0": {"dead_money": 50.0, "cap_transactions": 0.0, "rollover": 0.0},
            "Team 1": {"dead_money": 50.0, "cap_transactions": 0.0, "rollover": 0.0},
        },
    )

    assert env_with_adj["total_cap_available"] < env_no_adj["total_cap_available"]
    assert math.isclose(
        env_no_adj["total_cap_available"] - env_with_adj["total_cap_available"],
        100.0,  # 2 teams × $50 dead money
        rel_tol=1e-9,
    )


def test_rollover_backed_out_of_effective_cap():
    # cap_remaining per team = base_cap - usage + rollover = 300 - 100 + 30 = 230
    # 2 teams → total_cap_available = $460
    # total_rollover = 2 × $30 = $60
    # effective_cap_available = $460 - $60 = $400
    # CVR uses effective: 400 / 32 = 12.5; without rollover backing it would be 460 / 32 ≈ 14.375
    tv = _tv_df()
    cfg = _mini_config(base_cap=300.0, n_teams=2, alpha=0.5)
    cap_h = pd.DataFrame([
        {"team": "Team 0", "current_cap_usage": 100.0},
        {"team": "Team 1", "current_cap_usage": 100.0},
    ])
    adj = {
        "Team 0": {"dead_money": 0.0, "cap_transactions": 0.0, "rollover": 30.0},
        "Team 1": {"dead_money": 0.0, "cap_transactions": 0.0, "rollover": 30.0},
    }

    env = compute_cap_environment(tv, cap_h, cfg, team_adjustments=adj)

    assert math.isclose(env["total_cap_available"], 460.0, rel_tol=1e-9)
    assert math.isclose(env["total_rollover"], 60.0, rel_tol=1e-9)
    assert math.isclose(env["effective_cap_available"], 400.0, rel_tol=1e-9)
    # CVR and multiplier use effective, not total
    fa_value = 20.0 + 12.0  # from _tv_df(), FA players only
    expected_cpr = 400.0 / fa_value
    assert math.isclose(env["cap_to_value_ratio"], expected_cpr, rel_tol=1e-9)


def test_rollover_zero_when_no_adjustments():
    # No team adjustments → total_rollover = 0, effective = total
    tv = _tv_df()
    cfg = _mini_config(base_cap=300.0, n_teams=2, alpha=0.5)
    cap_h = _cap_health_df(cap_usage_per_team=100.0, n_teams=2)

    env = compute_cap_environment(tv, cap_h, cfg)

    assert math.isclose(env["total_rollover"], 0.0)
    assert math.isclose(env["effective_cap_available"], env["total_cap_available"])
