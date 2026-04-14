"""Position-specific age-curve multipliers for dynasty multi-year projections.

The model assumes each position has a peak age where a player is most likely to
fully realise their dynasty-implied ceiling ESV (multiplier = 1.0).  Before
that peak, ESV rises exponentially; after it, ESV decays exponentially.

Multiplier formula
------------------
Given:
  years_to_peak = peak_age - current_age      (negative if already past peak)
  rise_term     = max(0, years_to_peak - k)   (years still needed to reach peak)
  decline_term  = max(0, k - years_to_peak)   (years past peak at offset k)

  multiplier = exp(-rise_slope  * rise_term)
             * exp(-decline_slope * decline_term)

At k == years_to_peak the player is at their peak: both terms are 0 → multiplier = 1.0.
Pre-peak players have rise_term > 0 → multiplier < 1.0, increasing each year.
Post-peak players have decline_term > 0 → multiplier < 1.0, decreasing each year.

Config keys (under ``age_curves.<POSITION>`` in league_config.yaml)
--------------------------------------------------------------------
peak_age      : float  – age (years) at which multiplier = 1.0
rise_slope    : float  – exponential rate of pre-peak rise (per year, > 0)
decline_slope : float  – exponential rate of post-peak decline (per year, > 0)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_DEFAULT_CURVES: dict[str, dict] = {
    "QB": {"peak_age": 29.0, "rise_slope": 0.04, "decline_slope": 0.06},
    "WR": {"peak_age": 27.0, "rise_slope": 0.07, "decline_slope": 0.08},
    "RB": {"peak_age": 25.0, "rise_slope": 0.09, "decline_slope": 0.12},
    "TE": {"peak_age": 27.0, "rise_slope": 0.05, "decline_slope": 0.07},
}


@dataclass(frozen=True)
class AgeCurveParams:
    """Immutable age-curve parameters for one position."""

    peak_age: float
    rise_slope: float
    decline_slope: float


def load_age_curves(config: dict) -> dict[str, AgeCurveParams]:
    """Build position → ``AgeCurveParams`` mapping from a loaded config dict.

    Falls back to built-in defaults for any position not present in *config*.

    Parameters
    ----------
    config:
        Top-level dict from ``league_config.yaml`` (as returned by
        ``src.utils.config.load_config()``).

    Returns
    -------
    Dict mapping position string (e.g. ``"QB"``) to ``AgeCurveParams``.
    """
    raw = config.get("age_curves", {})
    result: dict[str, AgeCurveParams] = {}
    all_positions = set(_DEFAULT_CURVES) | set(str(k).upper() for k in raw)
    for pos in all_positions:
        src = raw.get(pos, raw.get(pos.lower(), _DEFAULT_CURVES.get(pos, {})))
        if not src:
            src = _DEFAULT_CURVES.get(pos, {})
        result[pos] = AgeCurveParams(
            peak_age=float(src.get("peak_age", 27.0)),
            rise_slope=float(src.get("rise_slope", 0.07)),
            decline_slope=float(src.get("decline_slope", 0.08)),
        )
    return result


def get_age_multiplier(
    params: AgeCurveParams,
    current_age: float,
    year_offset: int,
) -> float:
    """Return the age-curve multiplier for a player at ``current_age + year_offset``.

    Parameters
    ----------
    params:
        Position-specific curve parameters.
    current_age:
        Player's age at year 0 (the contract base year).  If NaN or non-finite,
        returns 1.0 (no adjustment).
    year_offset:
        Number of years into the future (0 = current season, 1 = next year, …).

    Returns
    -------
    Float in (0, 1] — 1.0 when the player is at their peak age, < 1.0 otherwise.
    """
    if not math.isfinite(current_age):
        return 1.0
    if year_offset < 0:
        raise ValueError(f"year_offset must be >= 0, got {year_offset}")

    years_to_peak = params.peak_age - current_age
    rise_term = max(0.0, years_to_peak - year_offset)
    decline_term = max(0.0, float(year_offset) - years_to_peak)
    return math.exp(-params.rise_slope * rise_term) * math.exp(-params.decline_slope * decline_term)


def get_age_multipliers(
    params: AgeCurveParams,
    current_age: float,
    max_offset: int = 3,
) -> list[float]:
    """Return multipliers for offsets 0, 1, …, ``max_offset`` (inclusive).

    Convenience wrapper around ``get_age_multiplier`` for building TV paths.
    """
    return [get_age_multiplier(params, current_age, k) for k in range(max_offset + 1)]
