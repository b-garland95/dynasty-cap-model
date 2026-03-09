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
    """
    if path is None:
        path_obj = Path(__file__).resolve().parents[1] / "config" / "league_config.yaml"
    else:
        path_obj = Path(path)

    with path_obj.open("r", encoding="utf-8") as fh:
        text = fh.read()

    if yaml is not None:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}

    return _parse_simple_yaml(text)


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
