"""Rookie pick activation curve and effective cap treatment.

Activation probability
----------------------
Each draft pick eventually becomes a player on a rookie-scale contract. In
League Tycoon contract leagues that player may remain on the practice squad
(25% cap rate) or be activated onto the active roster (full cap rate). For
cap-health projections we need an *expected* effective cap hit and an
*expected* effective value contribution for each pick.

The activation curve maps a pick's slot (1.01, 1.10, 2.05, …) to a
probability that the rookie is activated, p_activate. It is a log-style
decay anchored at the top of Round 1 and falling steeply into Round 2.

v1 curve parameters
-------------------
The curve is defined by three config-driven parameters that live under
``draft_picks.activation_curve`` in ``league_config.yaml``.  If the key is
absent, module-level defaults are used so existing configs do not break.

  alpha   – activation probability at slot 1 (default 0.92)
  beta    – log-decay rate (default 0.065)
  floor   – minimum activation probability for any slot (default 0.05)

  p_activate(slot) = max(floor, alpha * exp(-beta * (slot - 1)))

where ``slot`` is a continuous pick number across all rounds:
  Round 1, pick k  → slot k          (1 … 10)
  Round 2, pick k  → slot 10 + k     (11 … 20)
  Round 3, pick k  → slot 20 + k     (21 … 30)
  Round 4, pick k  → slot 30 + k     (31 … 40)

This guarantees strict monotonic decay: 1.01 > 1.10 > 2.01 > … > 4.10.

Effective cap/value formulas
-----------------------------
Expected effective cap hit:
    eff_cap = p_activate * full_cap + (1 - p_activate) * ps_cap

Expected effective value contribution:
    eff_value = p_activate * intrinsic_value + (1 - p_activate) * ps_value

where:
    ps_cap    = ps_cap_percent * full_cap   (25% by default, from config)
    ps_value  = ps_cap                       (same as ps cap; no surplus by design)
    intrinsic_value = full_cap               (value == cap for rookies)

The same ``p_activate`` is applied symmetrically to both cap and value so
that the activation discount is consistent across all downstream consumers.

Replacing the curve
-------------------
Downstream code should call ``activation_probability(slot, params)`` rather
than replicating the formula.  Swapping in a data-driven model later only
requires changing this one function (and the params dict that feeds it).
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Default curve parameters (used when config key is absent)
# ---------------------------------------------------------------------------

_DEFAULT_ALPHA = 0.92   # p_activate at slot 1
_DEFAULT_BETA = 0.065   # log-decay rate per slot
_DEFAULT_FLOOR = 0.05   # minimum activation probability


# ---------------------------------------------------------------------------
# Slot arithmetic
# ---------------------------------------------------------------------------

def pick_slot_number(rnd: int, slot_within_round: int, picks_per_round: int = 10) -> int:
    """Convert (round, slot_within_round) to a continuous slot number.

    Slot numbers start at 1 and are contiguous across rounds:
      (1, 1) → 1, (1, 10) → 10, (2, 1) → 11, …

    Parameters
    ----------
    rnd:
        Round number (1-based).
    slot_within_round:
        Pick position within the round (1-based).
    picks_per_round:
        Number of picks per round (default 10, from league config).

    Returns
    -------
    int  Continuous slot number ≥ 1.
    """
    return (rnd - 1) * picks_per_round + slot_within_round


# ---------------------------------------------------------------------------
# Activation curve
# ---------------------------------------------------------------------------

def _curve_params(config: dict[str, Any] | None) -> tuple[float, float, float]:
    """Extract (alpha, beta, floor) from config, falling back to defaults."""
    if config is None:
        return _DEFAULT_ALPHA, _DEFAULT_BETA, _DEFAULT_FLOOR
    ac = config.get("draft_picks", {}).get("activation_curve", {})
    alpha = float(ac.get("alpha", _DEFAULT_ALPHA))
    beta = float(ac.get("beta", _DEFAULT_BETA))
    floor = float(ac.get("floor", _DEFAULT_FLOOR))
    return alpha, beta, floor


def activation_probability(
    slot: int,
    config: dict[str, Any] | None = None,
) -> float:
    """Return the rookie activation probability for a continuous slot number.

    Parameters
    ----------
    slot:
        Continuous slot number (use ``pick_slot_number`` to convert from
        round + position).  Must be ≥ 1.
    config:
        Full league config dict.  If None, module defaults are used.

    Returns
    -------
    float in [floor, alpha].  Strictly decreasing with slot.
    """
    alpha, beta, floor = _curve_params(config)
    raw = alpha * math.exp(-beta * (slot - 1))
    return max(floor, raw)


# ---------------------------------------------------------------------------
# Effective cap / value
# ---------------------------------------------------------------------------

def effective_cap_hit(
    full_cap: float,
    p_activate: float,
    ps_cap_percent: float,
) -> float:
    """Expected effective cap hit blending active and PS cap rates.

    eff_cap = p_activate * full_cap + (1 - p_activate) * (ps_cap_percent * full_cap)

    Parameters
    ----------
    full_cap:
        Full active-roster cap hit ($).
    p_activate:
        Activation probability from ``activation_probability()``.
    ps_cap_percent:
        Practice-squad cap rate (e.g. 0.25 for 25%).

    Returns
    -------
    float  Expected cap burden ($).
    """
    ps_cap = ps_cap_percent * full_cap
    return p_activate * full_cap + (1.0 - p_activate) * ps_cap


def effective_value_contribution(
    intrinsic_value: float,
    p_activate: float,
    ps_cap_percent: float,
) -> float:
    """Expected effective value contribution.

    For rookie picks, intrinsic_value == full_cap (zero surplus by design).
    PS value is treated as ps_cap_percent * intrinsic_value to match the
    cap-discount convention.

    eff_value = p_activate * intrinsic_value + (1 - p_activate) * (ps_cap_percent * intrinsic_value)

    Parameters
    ----------
    intrinsic_value:
        Full-activation value contribution ($); equals full_cap for rookies.
    p_activate:
        Activation probability from ``activation_probability()``.
    ps_cap_percent:
        Practice-squad value rate (mirrors ps_cap_percent in cap formula).

    Returns
    -------
    float  Expected value contribution ($).
    """
    ps_value = ps_cap_percent * intrinsic_value
    return p_activate * intrinsic_value + (1.0 - p_activate) * ps_value


# ---------------------------------------------------------------------------
# High-level convenience: pick effective economics
# ---------------------------------------------------------------------------

def pick_effective_economics(
    rnd: int,
    slot_within_round: int | None,
    full_cap_current_year: float,
    config: dict[str, Any],
) -> dict[str, float]:
    """Return activation-discounted cap and value for a single pick.

    Parameters
    ----------
    rnd:
        Round number (1–4).
    slot_within_round:
        Pick position within the round (1-based), or None if order unknown.
        When None, the mid-point of the round is used as a slot estimate
        so the result is still directionally correct.
    full_cap_current_year:
        The pick's full active-roster cap hit for the current year (from
        ``pick_value_metrics``'s ``cap_y0`` / ``value_1yr`` when offset=0,
        or 0 if the pick is a future-year pick).
    config:
        Full league config dict.

    Returns
    -------
    dict with keys:
        slot               : int  continuous slot used for the curve
        p_activate         : float  activation probability
        full_cap           : float  full active-roster cap (input)
        ps_cap             : float  practice-squad cap (ps_percent * full_cap)
        eff_cap_hit        : float  expected effective cap hit
        eff_value          : float  expected effective value contribution
        ps_cap_percent     : float  PS rate sourced from config
    """
    dp_cfg = config.get("draft_picks", {})
    picks_per_round = int(dp_cfg.get("picks_per_round", 10))

    # When draft order is unknown use the round midpoint as a slot estimate.
    if slot_within_round is None:
        slot_within_round = (picks_per_round // 2) + 1

    slot = pick_slot_number(rnd, slot_within_round, picks_per_round)
    p_act = activation_probability(slot, config)

    ps_cfg = config.get("practice_squad", {})
    ps_percent = float(ps_cfg.get("cap_percent", 0.25))

    eff_cap = effective_cap_hit(full_cap_current_year, p_act, ps_percent)
    eff_val = effective_value_contribution(full_cap_current_year, p_act, ps_percent)

    return {
        "slot": slot,
        "p_activate": p_act,
        "full_cap": full_cap_current_year,
        "ps_cap": ps_percent * full_cap_current_year,
        "eff_cap_hit": eff_cap,
        "eff_value": eff_val,
        "ps_cap_percent": ps_percent,
    }
