# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Dynasty Cap Model is a salary-cap dynasty fantasy football valuation framework for **League Tycoon** contract leagues. The repo is a test-driven pipeline that goes from historical weekly stats → season values (PAR/SAV/ESV/LD/CG) → predictive TV forecasts → contract surplus/dead-money/instrument-decision tables.

Platform rules reference: https://leaguetycoon.com/rules/contract-league-rules/
nflreadpy Github and docs: https://github.com/nflverse/nflreadpy 

## Commands

```bash
# Env setup
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

# Run all tests (must pass on every milestone)
python -m pytest -q

# Run a single test file / single test
python -m pytest tests/test_phase3_tables.py -q
python -m pytest tests/test_phase1_assignment.py::test_name -q

# Pipeline scripts (scripts/)
python scripts/normalize_weekly_projections.py
python scripts/build_master_weekly_projections.py
python scripts/load_historical_weekly_points.py
python scripts/normalize_historical_weekly_points.py
python scripts/export_phase3_tables.py
python scripts/run_phase3_qa.py
# R script for nflverse stats export:
Rscript scripts/export_nflverse_player_stats.R
```

## Architecture

Source tree is organized by pipeline phase, not by data type:

- `src/config/league_config.yaml` — **single source of truth** for all league rules (roster slots, escalators, dead-money %, PS/IR cap hits, rookie scale, discount rate). Never hardcode league settings elsewhere; read via `src/utils/config.py`.
- `src/ingest/` — raw → normalized loaders (League Tycoon rosters, FantasyData weekly projections, historical weekly points). Handles both legacy (2014–2024) and current schema variants and unifies them into a common `season/week/player_id/…/projected_points` shape.
- `src/valuation/` — **Phase 1** historical season valuation: weekly slot cutlines, shrinkage, constrained lineup assignment, SAV, ESV, LD, CG.
- `src/modeling/` — **Phase 2** predictive layer: position-specific monotonic ADP→ESV calibration with quantiles, rolling time-aware backtests. Target is season ESV, not raw points.
- `src/contracts/` — **Phase 3** contract math: dead money, salary schedules, PV @ 25% discount, surplus, instrument (extension/tag/option) evaluation.
- `scripts/` — thin entry points that wire ingest → valuation/modeling → contracts and write to `data/{raw,interim,processed}/`.
- `tests/fixtures/` — tiny golden fixtures; every milestone ships with unit tests.

### Phase 1 mechanics that are easy to get wrong

- **Two levels of cutlines**: **Slot cutlines** (QB, RB, WR, TE, FLEX, SF) are computed via a weekly leaguewide optimal constrained allocation and determine who starts. **Position cutlines** (the min points of any starter of that position across all slots) are used for margin/WMSV calculation. Both are shrunk toward a season baseline.
- **Players cannot choose their best slot.** The assignment determines who starts and in which slot. Margins are computed against the player's **position cutline**, not their assigned slot's cutline. This ensures all QBs are valued against the same replacement level whether they fill the QB or SF slot.
- Expected Start Value (ESV) discounts SAV by roster/start probabilities in a rational average league; LD penalizes sub-replacement starts; `CG = SAV - ESV`.

### Phase 3 contract invariants

- **Real Salary** drives contract PV and dead money. **Current Salary** is only used for "cap today" feasibility (PS/IR discounted).
- Standard escalation in this league is **+10%/yr** (LT default is 0%). PS cap hit 25%, IR cap hit 75% (LT default 100%). Discount rate 25%.
- Dead money on active-roster cut: 100% of current year + `25% × (years_remaining − 1) × salary` as a single lump sum next season; `$0` in year 3+. Use ceil rounding (see commit 78c72ad).
- Any deal where `has_been_extended` or `has_been_tagged` (or later, optioned) **must** set `needs_schedule_validation = true` unless an observed year-by-year schedule is supplied. Instrument-adjusted deals can break the +10% escalator.
- League Tycoon exports' `Extension Salary` column is the pre-computed performance-based extension value (5-step LT calc using 85% of market salary, $10 floor). Large gap vs `Real Salary` = breakout candidate.

### Milestone discipline

Work is organized in tight milestones (see README "Development Workflow"). **Do not bundle multiple milestones into one change set.** Every milestone ships unit tests; if a rule is ambiguous, add a TODO plus a failing test placeholder rather than guessing.

### Name/ID normalization

Names differ across LT exports, FantasyPros ADP, and projection sources. A name map layer lives at `data/external/name_map.csv` (as it materializes); prefer a normalized `player_id` as the join key. Legacy 2014–2024 projections can contain duplicate `(season, week, player_id)` rows from mid-week team changes — master-build resolution keeps the higher `projected_points`, ties keep the first row.
