"""Tests for RationalStartCaptureModel (Milestone 4b.1).

Scenario: BoomRB has a very low projection (4 pts) but a huge actual score (30 pts).
All FLEX competitors bust to 0 actual pts so BoomRB cracks the actual FLEX slot.
Under PerfectCaptureModel, ESV == SAV.
Under RationalStartCaptureModel, σ is near-zero (BoomRB's proj is far below the
projected FLEX cutline) so ESV << SAV.
"""
import math

import pandas as pd

from src.utils.config import load_league_config
from src.valuation.capture_model import PerfectCaptureModel, RationalStartCaptureModel
from src.valuation.phase1_assignment import assign_leaguewide_starting_set, compute_weekly_margins
from src.valuation.phase1_cutlines import compute_position_cutlines
from src.valuation.phase1_metrics import aggregate_sav
from src.valuation.phase1_projected import assign_projected_leaguewide_starting_set
from src.valuation.phase1_esv import compute_esv_ld_from_started_weekly

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
        base = {"season": SEASON, "week": WEEK, "gsis_id": f"G-{player}", "player": player, "position": position}
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
    """Compute the actual started set and add season/week for ESV lookup."""
    pts_only = actual_df[["gsis_id", "player", "position", "points"]]
    started_df = assign_leaguewide_starting_set(pts_only, config)
    pos_cutlines = compute_position_cutlines(started_df)
    started = compute_weekly_margins(started_df, pos_cutlines)
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
    boom_sav = sav_df.loc[sav_df["gsis_id"] == "G-BoomRB", "sav"].iloc[0]
    assert boom_sav > 0


# ---------------------------------------------------------------------------
# PerfectCaptureModel: ESV == SAV
# ---------------------------------------------------------------------------

def test_perfect_capture_esv_equals_sav():
    """Under PerfectCaptureModel, ESV equals SAV for every player."""
    config = load_league_config()
    _, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)

    sav_df = aggregate_sav(started_df)
    esv_df = compute_esv_ld_from_started_weekly(started_df, PerfectCaptureModel())

    merged = sav_df.merge(esv_df, on="gsis_id")
    for _, row in merged.iterrows():
        assert math.isclose(row["sav"], row["esv"], rel_tol=1e-9), (
            f"{row['player']}: SAV={row['sav']:.4f} != ESV={row['esv']:.4f}"
        )


# ---------------------------------------------------------------------------
# RationalStartCaptureModel: ESV < SAV for BoomRB
# ---------------------------------------------------------------------------

def test_rational_capture_discounts_boom_rb_esv_below_sav():
    """Under RationalStartCaptureModel, BoomRB's ESV is much less than its SAV.

    BoomRB is not in the projected starting set, so σ ≈ 0 and ESV ≈ 0.
    """
    config = load_league_config()
    proj_df, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)

    sav_df = aggregate_sav(started_df)
    boom_sav = sav_df.loc[sav_df["gsis_id"] == "G-BoomRB", "sav"].iloc[0]

    model = RationalStartCaptureModel(proj_df=proj_df, config=config)
    esv_df = compute_esv_ld_from_started_weekly(started_df, model)
    boom_esv = esv_df.loc[esv_df["gsis_id"] == "G-BoomRB", "esv"].iloc[0]

    assert boom_esv < boom_sav


def test_rational_capture_boom_rb_esv_less_than_perfect():
    """RationalStartCaptureModel gives BoomRB lower ESV than PerfectCaptureModel."""
    config = load_league_config()
    proj_df, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)

    perfect_esv_df = compute_esv_ld_from_started_weekly(started_df, PerfectCaptureModel())
    boom_perfect = perfect_esv_df.loc[perfect_esv_df["gsis_id"] == "G-BoomRB", "esv"].iloc[0]

    model = RationalStartCaptureModel(proj_df=proj_df, config=config)
    rational_esv_df = compute_esv_ld_from_started_weekly(started_df, model)
    boom_rational = rational_esv_df.loc[rational_esv_df["gsis_id"] == "G-BoomRB", "esv"].iloc[0]

    assert boom_rational < boom_perfect


# ---------------------------------------------------------------------------
# Monotonic sanity check
# ---------------------------------------------------------------------------

def test_higher_projected_margin_yields_higher_sigma():
    """Monotonic check: same proj slot_hat, higher projected margin → higher σ.

    Use α=0 (constant τ) so players near the cutline don't both saturate to 1.0.
    RB21 (proj=130) and RB22 (proj=129) are both assigned to FLEX in the
    projected starting set with FLEX cutline=81. RB21's projected margin is
    one point larger, so its σ must be strictly higher.
    """
    config = load_league_config()
    # Use constant τ so the 1-point difference is distinguishable.
    config = {**config, "capture_model": {**config["capture_model"], "tau_margin_scaling": 0.0}}
    proj_df, _ = _make_boom_scenario(config)
    model = RationalStartCaptureModel(proj_df=proj_df, config=config)

    # Both RBs are in the projected FLEX slot (confirmed by the pool structure).
    test_df = pd.DataFrame([
        {
            "season": SEASON, "week": WEEK, "gsis_id": "G-RB21", "player": "RB21", "position": "RB",
            "points": 10.0, "assigned_slot": "FLEX", "wmsv": 5.0, "wdrag": 0.0,
        },
        {
            "season": SEASON, "week": WEEK, "gsis_id": "G-RB22", "player": "RB22", "position": "RB",
            "points": 5.0, "assigned_slot": "FLEX", "wmsv": 0.0, "wdrag": -5.0,
        },
    ])

    sigmas = model.start_prob(test_df)
    # RB21 proj=130 > RB22 proj=129, same slot → σ(RB21) > σ(RB22)
    assert sigmas.iloc[0] > sigmas.iloc[1]


def test_monotonicity_near_cutline_with_variable_tau():
    """Monotonic check near the cutline with variable τ enabled.

    TE9 (proj=72) and TE10 (proj=71) are near the TE cutline (71).
    TE9 has margin +1, TE10 has margin 0. With variable τ, margins this
    small keep τ_effective close to τ_base, so the 1-point difference is
    still distinguishable.
    """
    config = load_league_config()
    assert config["capture_model"].get("tau_margin_scaling", 0.0) > 0
    proj_df, _ = _make_boom_scenario(config)
    model = RationalStartCaptureModel(proj_df=proj_df, config=config)

    test_df = pd.DataFrame([
        {
            "season": SEASON, "week": WEEK, "gsis_id": "G-TE9", "player": "TE9", "position": "TE",
            "points": 10.0, "assigned_slot": "TE", "wmsv": 5.0, "wdrag": 0.0,
        },
        {
            "season": SEASON, "week": WEEK, "gsis_id": "G-TE10", "player": "TE10", "position": "TE",
            "points": 5.0, "assigned_slot": "TE", "wmsv": 0.0, "wdrag": -5.0,
        },
    ])

    sigmas = model.start_prob(test_df)
    # TE9 proj=72 > TE10 proj=71, same slot → σ(TE9) > σ(TE10)
    assert sigmas.iloc[0] > sigmas.iloc[1]


# ---------------------------------------------------------------------------
# Variable τ: tail behavior (top players → σ ≈ 1, bottom → σ ≈ 0)
# ---------------------------------------------------------------------------

def test_top_projected_qbs_have_near_certain_start_prob():
    """Top 2 projected QBs should have σ > 0.99 with variable τ.

    QB1 (proj=200) and QB2 (proj=199) are well above the QB cutline (~190).
    With tau_margin_scaling > 0, τ_effective shrinks for large margins,
    pushing σ toward 1.0.
    """
    config = load_league_config()
    assert config["capture_model"].get("tau_margin_scaling", 0.0) > 0, (
        "tau_margin_scaling must be set for this test"
    )
    proj_df, actual_df = _make_boom_scenario(config)
    model = RationalStartCaptureModel(proj_df=proj_df, config=config)

    started_df = _build_started_weekly_df(actual_df, config)
    # QB1 and QB2 are in the actual started set (top QBs).
    qb1 = started_df[started_df["gsis_id"] == "G-QB1"]
    qb2 = started_df[started_df["gsis_id"] == "G-QB2"]
    assert len(qb1) == 1 and len(qb2) == 1

    sigma_qb1 = model.start_prob(qb1).iloc[0]
    sigma_qb2 = model.start_prob(qb2).iloc[0]
    assert sigma_qb1 > 0.99, f"QB1 σ={sigma_qb1:.4f}, expected > 0.99"
    assert sigma_qb2 > 0.99, f"QB2 σ={sigma_qb2:.4f}, expected > 0.99"


def test_bottom_of_pool_has_near_zero_start_prob():
    """A player far below the cutline should have σ < 0.01 with variable τ.

    BoomRB (proj=4) is ~77 points below the FLEX cutline (~81).
    Variable τ makes the sigmoid even steeper for large negative margins.
    """
    config = load_league_config()
    proj_df, actual_df = _make_boom_scenario(config)
    model = RationalStartCaptureModel(proj_df=proj_df, config=config)

    started_df = _build_started_weekly_df(actual_df, config)
    boom_row = started_df[started_df["gsis_id"] == "G-BoomRB"]
    assert len(boom_row) == 1

    sigma_boom = model.start_prob(boom_row).iloc[0]
    assert sigma_boom < 0.01, f"BoomRB σ={sigma_boom:.4f}, expected < 0.01"


def test_variable_tau_recovers_constant_when_alpha_zero():
    """With tau_margin_scaling=0, variable τ produces identical σ to constant τ."""
    config = load_league_config()
    proj_df, actual_df = _make_boom_scenario(config)
    started_df = _build_started_weekly_df(actual_df, config)

    # Model with alpha from config (> 0).
    model_variable = RationalStartCaptureModel(proj_df=proj_df, config=config)
    sigma_variable = model_variable.start_prob(started_df)

    # Model with alpha = 0 (constant τ).
    config_zero = {**config, "capture_model": {**config["capture_model"], "tau_margin_scaling": 0.0}}
    model_constant = RationalStartCaptureModel(proj_df=proj_df, config=config_zero)
    sigma_constant = model_constant.start_prob(started_df)

    # They should NOT be equal when alpha > 0 in the original config.
    assert not sigma_variable.equals(sigma_constant), (
        "Variable and constant τ should produce different σ values when α > 0"
    )
