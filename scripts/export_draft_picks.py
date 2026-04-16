"""Export draft pick inventory (with ownership) to a CSV for the dashboard.

Reads:
  - src/config/league_config.yaml  (pick universe: years, rounds, salaries)
  - data/processed/draft_pick_ownership.json  (who owns each pick)

Writes:
  - data/processed/draft_pick_inventory.csv

The dashboard symlink dashboard/data/draft_pick_inventory.csv points to this
output file.

Usage:
    python scripts/export_draft_picks.py

Columns in the output CSV:
  pick_id, year, round, slot, salary, owner
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Ensure src/ is importable when running as a top-level script.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.config import load_league_config
from src.contracts.draft_picks import generate_picks, load_ownership, build_inventory_table

OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "draft_pick_inventory.csv"
FIELDNAMES = ["pick_id", "year", "round", "slot", "salary", "owner"]


def main() -> None:
    config = load_league_config()
    picks = generate_picks(config)
    ownership = load_ownership()
    rows = build_inventory_table(picks, ownership)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (row[k] if row[k] is not None else "") for k in FIELDNAMES})

    print(f"Exported {len(rows)} picks to {OUTPUT_PATH}")
    year_counts: dict[int, int] = {}
    for r in rows:
        year_counts[r["year"]] = year_counts.get(r["year"], 0) + 1
    for year, count in sorted(year_counts.items()):
        owned = sum(1 for r in rows if r["year"] == year and r["owner"])
        print(f"  {year}: {count} picks, {owned} assigned")


if __name__ == "__main__":
    main()
