"""Tests for RationalStartCaptureModel (Milestone 4b.1).

Scenario: BoomRB has a very low projection (4 pts) but a huge actual score (30 pts).
All FLEX competitors bust to 0 actual pts so BoomRB cracks the actual FLEX slot.
Under PerfectCaptureModel, RSV == SAV.
Under RationalStartCaptureModel, σ is near-zero (BoomRB's proj is far below the
projected FLEX cutline) so RSV << SAV.
"""
import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.capture_model import PerfectCaptureModel, RationalStartCaptureModel
from src.valuation.phase1_assignment import compute_sav_for_week
from src.valuation.phase1_cutlines import compute_weekly_raw_cutlines
from src.valuation.phase1_metrics import aggregate_sav
from src.valuation.phase1_projected import assign_projected_leaguewide_starting_set
from src.valuation.phase1_realized import compute_rsv_ld_from_started_weekly

SEASON, WEEK = 2024, 1


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_boom_scenario(config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build projection and actual DataFrames for the BoomRB scenario.

    Pool: 12 QBs, 30 regular RBs + BoomRB, 45 WRs, 18 TEs.

    Projections
    -----------
    BoomRB has proj_points=4, far below the projected FLEX cutline (~81).
    All other players carry normal descending projected points so the projected
    slot structure matches the existing test fixtures exactly.

    Actuals
    -------
    BoomRB has actual_points=30 (a boom week).
    RB21-30, WR31-45, and TE11-18 all bust to 0 actual pts, collapsing the
    actual FLEX cutline to 0 so BoomRB enters the actual starting set.
    """
    proj_rows: list[dict] = []
    actual_rows: list[dict] = []

    def _add(player: str, position: str, proj: float, actual: float) -> None:
        base = {"season": SEASON, "week": WEEK, "player": player, "position": position}
        proj_rows.append({**base, "proj_points": proj})
        actual_rows.append({**base, "points": actual})

    for i in range(1, 13):
        _add(f"QB{i}", "QB", proj=201 - i, actual=201 - i)

    for i in range(1, 31):
        _add(f"RB{i}", "RB", proj=151 - i, actual=(151 - i) if i <= 20 else 0)

    # BoomRB: low projection, huge actual
    _add("BoomRB", "RB", proj=4.0, actual=30.0)

    for i in range(1, 46):
        _add(f"WR{i}", "WR", proj=121 - i, actual=(121 - i) if i <= 30 else 0)

    for i in range(1, 19):
        _add(f"TE{i}", "TE", proj=81 - i, actual=(81 - i) if i <= 10 else 0)

    return pd.DataFrame(proj_rows), pd.DataFrame(actual_rows)


def _build_started_weekly_df(actual_df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Compute the actual started set and add season/week for RSV lookup."""
    pts_only = actual_df[["player", "position", "points"]]
    cutlines = compute_weekly_raw_cutlines(pts_only, config)
    started = compute_sav_for_week(pts_only, cutlines, config)
    started["season"] = SEASON
    started["week"] = WEEK
    return started


# ---------------------------------------------------------------------------
# Structural checks (projected vs actual starting set membership)
# ---------------------------------------------------------------------------

def test_boom_rb_not_in_projected_starting_set():
    """BoomRB (proj=4) should not appear in the projected leaguewide starting set."""
    config = load_league_config()
    proj_df, _ = _make_boom_scenario(config)
    proj_started = assign_projected_leaguewide_starting_set(proj_df, config)
    assert "BoomRB" not in proj_started["player"].values


def test_boom_rb_is_in_actual_started_set():
    """BoomRB (actual=30, FLEX cutline=0) should appear in the actual starting set."""
    config = load_league_config()
    _, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)
    assert "BoomRB" in started_df["player"].values


def test_boom_rb_actual_sav_is_positive():
    """BoomRB earns positive SAV because actual points (30) > actual FLEX cutline (0)."""
    config = load_league_config()
    _, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)
    sav_df = aggregate_sav(started_df)
    boom_sav = sav_df.loc[sav_df["player"] == "BoomRB", "sav"].iloc[0]
    assert boom_sav > 0


# ---------------------------------------------------------------------------
# PerfectCaptureModel: RSV == SAV
# ---------------------------------------------------------------------------

def test_perfect_capture_rsv_equals_sav():
    """Under PerfectCaptureModel, RSV equals SAV for every player."""
    config = load_league_config()
    _, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)

    sav_df = aggregate_sav(started_df)
    rsv_df = compute_rsv_ld_from_started_weekly(started_df, PerfectCaptureModel())

    merged = sav_df.merge(rsv_df, on="player")
    for _, row in merged.iterrows():
        assert math.isclose(row["sav"], row["rsv"], rel_tol=1e-9), (
            f"{row['player']}: SAV={row['sav']:.4f} != RSV={row['rsv']:.4f}"
        )


# ---------------------------------------------------------------------------
# RationalStartCaptureModel: RSV < SAV for BoomRB
# ---------------------------------------------------------------------------

def test_rational_capture_discounts_boom_rb_rsv_below_sav():
    """Under RationalStartCaptureModel, BoomRB's RSV is much less than its SAV.

    BoomRB is not in the projected starting set, so σ ≈ 0 and RSV ≈ 0.
    """
    config = load_league_config()
    proj_df, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)

    sav_df = aggregate_sav(started_df)
    boom_sav = sav_df.loc[sav_df["player"] == "BoomRB", "sav"].iloc[0]

    model = RationalStartCaptureModel(proj_df=proj_df, config=config)
    rsv_df = compute_rsv_ld_from_started_weekly(started_df, model)
    boom_rsv = rsv_df.loc[rsv_df["player"] == "BoomRB", "rsv"].iloc[0]

    assert boom_rsv < boom_sav


def test_rational_capture_boom_rb_rsv_less_than_perfect():
    """RationalStartCaptureModel gives BoomRB lower RSV than PerfectCaptureModel."""
    config = load_league_config()
    proj_df, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)

    perfect_rsv_df = compute_rsv_ld_from_started_weekly(started_df, PerfectCaptureModel())
    boom_perfect = perfect_rsv_df.loc[perfect_rsv_df["player"] == "BoomRB", "rsv"].iloc[0]

    model = RationalStartCaptureModel(proj_df=proj_df, config=config)
    rational_rsv_df = compute_rsv_ld_from_started_weekly(started_df, model)
    boom_rational = rational_rsv_df.loc[rational_rsv_df["player"] == "BoomRB", "rsv"].iloc[0]

    assert boom_rational < boom_perfect


# ---------------------------------------------------------------------------
# Monotonic sanity check
# ---------------------------------------------------------------------------

def test_higher_projected_margin_yields_higher_sigma():
    """Monotonic check: same proj slot_hat, higher projected margin → higher σ.

    RB21 (proj=130) and RB22 (proj=129) are both assigned to FLEX in the
    projected starting set. RB21's projected margin vs the FLEX cutline is
    one point larger, so its σ must be strictly higher.
    """
    config = load_league_config()
    proj_df, _ = _make_boom_scenario(config)
    model = RationalStartCaptureModel(proj_df=proj_df, config=config)

    # Both RBs are in the projected FLEX slot (confirmed by the pool structure).
    test_df = pd.DataFrame([
        {
            "season": SEASON, "week": WEEK, "player": "RB21", "position": "RB",
            "points": 10.0, "assigned_slot": "FLEX", "wmsv": 5.0, "wdrag": 0.0,
        },
        {
            "season": SEASON, "week": WEEK, "player": "RB22", "position": "RB",
            "points": 5.0, "assigned_slot": "FLEX", "wmsv": 0.0, "wdrag": -5.0,
        },
    ])

    sigmas = model.start_prob(test_df)
    # RB21 proj=130 > RB22 proj=129, same slot → σ(RB21) > σ(RB22)
    assert sigmas.iloc[0] > sigmas.iloc[1]
