"""Fetch and cache nflreadpy player dimension data.

Downloads the full player-dimensions table from nflreadpy and writes it to
``data/interim/player_dimensions_raw.csv``.  Subsequent pipeline scripts that
need player dimensions can pass this path as ``cache_path`` to
``load_player_dimensions()`` for offline / CI runs without a live network hit.

Usage:
    python scripts/load_player_dimensions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.player_dimensions import load_player_dimensions

OUTPUT_PATH = REPO_ROOT / "data" / "interim" / "player_dimensions_raw.csv"


def main() -> int:
    print("Fetching player dimensions from nflreadpy ...")
    dims = load_player_dimensions(cache_path=OUTPUT_PATH, refresh=True)
    print(f"Wrote {len(dims)} rows to {OUTPUT_PATH}")
    print(f"Columns: {list(dims.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
