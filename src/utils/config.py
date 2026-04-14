from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - environment-dependent
    yaml = None


def load_league_config(path: str | None = None) -> dict[str, Any]:
    """
    Load league configuration YAML as a dictionary.

    If `path` is not provided, loads `src/config/league_config.yaml`.
    Raises ``ValueError`` if required top-level keys are missing or values
    are obviously out of range.
    """
    if path is None:
        path_obj = Path(__file__).resolve().parents[1] / "config" / "league_config.yaml"
    else:
        path_obj = Path(path)

    with path_obj.open("r", encoding="utf-8-sig") as fh:
        text = fh.read()

    if yaml is not None:
        data = yaml.safe_load(text)
        config = data if isinstance(data, dict) else {}
    else:
        config = _parse_simple_yaml(text)

    validate_league_config(config)
    return config


def validate_league_config(config: dict[str, Any]) -> None:
    """Validate that required config keys exist and are in plausible ranges.

    Raises ``ValueError`` with a descriptive message on the first problem found.
    Call this at pipeline entry points to catch config errors early.
    """
    _require_keys(config, ["league", "lineup", "roster", "cap", "valuation",
                            "capture_model", "season", "player_positions"])

    _require_keys(config["league"], ["teams", "scoring"], parent="league")
    _require_keys(config["lineup"], ["qb", "rb", "wr", "te", "flex", "superflex"],
                  parent="lineup")
    _require_keys(config["cap"], ["base_cap", "annual_inflation", "discount_rate"],
                  parent="cap")
    _require_keys(config["season"], ["regular_weeks", "playoff_weeks",
                                     "num_regular_weeks", "current_season",
                                     "target_season", "history_start_season"],
                  parent="season")
    _require_keys(config["valuation"], ["shrinkage_lambdas"], parent="valuation")

    positions = config.get("player_positions")
    if not isinstance(positions, list) or not positions:
        raise ValueError("Config: player_positions must be a non-empty list")

    discount_rate = float(config["cap"]["discount_rate"])
    if not (0.0 < discount_rate < 1.0):
        raise ValueError(
            f"Config: cap.discount_rate must be between 0 and 1, got {discount_rate}"
        )

    annual_inflation = float(config["cap"]["annual_inflation"])
    if not (0.0 <= annual_inflation <= 1.0):
        raise ValueError(
            f"Config: cap.annual_inflation must be between 0 and 1, got {annual_inflation}"
        )

    teams = int(config["league"]["teams"])
    lineup = config["lineup"]
    total_starters = sum(
        teams * int(lineup[k])
        for k in ("qb", "rb", "wr", "te", "flex", "superflex")
    )
    if total_starters <= 0:
        raise ValueError(
            f"Config: total starters (teams × lineup slots) must be > 0, got {total_starters}"
        )

    current_season = int(config["season"]["current_season"])
    target_season = int(config["season"]["target_season"])
    if target_season < current_season:
        raise ValueError(
            f"Config: season.target_season ({target_season}) must be >= "
            f"season.current_season ({current_season})"
        )


def _require_keys(d: dict[str, Any], keys: list[str], parent: str = "config") -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(
            f"Config: missing required keys in {parent!r}: {missing}"
        )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a limited YAML subset used by league_config.yaml."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        key_part, _, value_part = line.strip().partition(":")
        key = _parse_key(key_part.strip())
        value_part = value_part.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if value_part == "":
            nested: dict[str, Any] = {}
            current[key] = nested
            stack.append((indent, nested))
        else:
            current[key] = _parse_scalar(value_part)

    return root


def _parse_key(raw: str) -> str:
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return raw


def _parse_scalar(raw: str) -> Any:
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    if raw.startswith("[") and raw.endswith("]"):
        return ast.literal_eval(raw)

    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        pass

    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return raw
