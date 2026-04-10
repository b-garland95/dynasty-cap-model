# Dynasty Cap Model

A salary-cap dynasty fantasy football valuation framework for League Tycoon-style contract leagues.

This repo implements a rigorous, test-driven pipeline to:
1) value historical player seasons beyond basic PAR
2) calibrate preseason ADP into expected season value (RSV) and uncertainty
3) translate multi-year expected value into contract surplus under League Tycoon mechanics
4) generate actionable Phase 3 tables for trades, contract management, and instrument decisions (extensions/tags/options)

---

## League Rules (Source of Truth)

All league rules must be read from:

- `src/config/league_config.yaml`

Do **not** hardcode league settings in Python modules. If a rule needs to change, it should be changed in config and tests should reflect it.

Current assumptions (see YAML for exact values):
- Teams: 10
- Scoring: Half PPR
- Starters: QB1, RB2, WR3, TE1, FLEX2 (RB/WR/TE), SF1 (QB/RB/WR/TE)
- Bench: 8, IR: 3, Practice Squad: 10
- Standard contract escalation: +10% per year
- Dead money (active roster cut): 100% current year + 25% of each future year remaining
- PS cap hit: 25%; IR cap hit: 75%
- Rookie scale: deterministic salaries by pick/round; 3-year rookie deal + 1-year option
- Option is use-it-or-lose-it each year; 1 option per team per year
- Discount rate for dynasty PV: 25%

---

## Core Definitions

### Phase 1 metrics (historical seasons)

We compute a ladder of season values:

- **PAR (naive baseline):** points above a crude position-only replacement
- **SAV (Slot-Adjusted Value):** value relative to leaguewide slot economy (FLEX/SF correctly handled), assuming perfect capture
- **RSV (Realized Start Value):** SAV discounted by roster/start probabilities in a rational average league
- **LD (Lineup Drag):** negative value from starts below replacement (penalizes durable mediocrity traps)
- **CG (Capture Gap):** `CG = SAV - RSV` (hindsight value that was not realistically captured)

### True Value vs Free Agent Value

- **True Value (TV):** value for all players, regardless of availability  
  - In v1, TV is measured in **RSV units**.
  - Later, TV may be upgraded to a win-based unit (tWARP/WPA).
- **Free Agent Value (FAV):** expected market-clearing auction price conditional on the FA auction pool and available cap.
  - FAV is a pricing layer, not a universal truth unit.

---

## Phase 1 Method (Historical Valuation)

### Weekly slot economy (replacement cutlines)
For each week, we compute replacement cutlines by slot type:

- QB, RB, WR, TE, FLEX (RB/WR/TE), SF (QB/RB/WR/TE)

Cutlines are computed via a deterministic leaguewide optimal allocation of actual points under lineup constraints.

### Shrinkage
Weekly cutlines are shrunk toward a season baseline to reduce noise:
`R_{s,w} = Î»_s * R_base_s + (1-Î»_s) * R_raw_{s,w}`

### Assignment (non-negotiable)
Players **cannot** choose the slot that maximizes their value.

Each week we compute an optimal constrained starting set and record each started player's **assigned slot**. Weekly margin is computed against the cutline of that assigned slot.

This prevents artifacts like â€œRB21 looks more valuable than RB20 because it was compared to FLEX.â€

---

## Phase 2 Method (Predictive Modeling)

### Target
Primary prediction target is season **RSV** (not raw points).

### v0: ADP-only calibration
We fit a position-specific monotonic mapping from preseason Superflex redraft ADP to expected RSV and quantiles:
- `RSV_hat = f_pos(log(ADP))`
- Quantiles (p25/p50/p75) for uncertainty bands

### Validation
Backtests must be time-aware:
- train on years â‰¤ t-1, test year t
Report:
- MAE on RSV
- Spearman rank correlation
- interval calibration (coverage)

---

## Phase 3 Method (Dynasty + Contracts)

### Per-year value path
We estimate expected True Value (RSV units) for the next 4 years:
`TV_y0..TV_y3`

### Dynasty PV
Discounted PV with d=25%:
`PV_TV = Î£ TV_yk / 1.25^k`

### Contracts
- **Real Salary** drives contract PV and dead money
- **Current Salary** is only used for â€œcap todayâ€ feasibility

Standard contract schedule (unless overridden by observed schedule):
`Cap_{t+k} = RealSalary * 1.1^k`

Instrument-adjusted deals (extended/tagged/optioned) can break standard escalation.
These must be flagged for schedule validation unless an observed year-by-year schedule is provided.

---

## Phase 3 v1 Outputs (Tables 1â€“7)

v1 focuses on these outputs (DataFrames/CSVs):

1) Player Contract Ledger (normalized LT export + derived flags)
2) Contract Salary Schedule (year-by-year; with schedule source + validation flags)
3) Production Value Forecast (TV path y0â€“y3 + PV @ 25%)
4) Contract Economics (cap PV + dead money exposure)
5) Contract Surplus & Trade Value (PV(TV) vs PV(cap) pair; full CSV once exchange rate exists)
6) Team Cap Health Dashboard (current vs real cap usage, PV burdens, validation exposure)
7) Instrument Candidate Shortlists (extension/tag/option; â€œuse only if surplus-positiveâ€)

---

## Invariants (Do Not Violate)

- League rules live only in `src/config/league_config.yaml`. Do not hardcode league settings elsewhere.
- Phase 1 cutlines are computed by slot (QB,RB,WR,TE,FLEX,SF) using leaguewide optimal allocation.
- Players cannot choose the slot that maximizes value. Assignment defines slot for margin calculations.
- Phase 3: Real Salary drives contract PV and dead money; Current Salary is only for â€œcap today.â€
- Any extended/tagged/optioned deal must set `needs_schedule_validation=true` unless an observed year-by-year schedule is provided.
- Tests are mandatory for every milestone (`python -m pytest -q` must pass).

---

## Getting Started (Local)

Create and activate a virtual environment, then install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# source .venv/Scripts/activate  # Git Bash on Windows
python -m pip install -r requirements.txt
python -m pytest -q
```

---

## Development Workflow

We build in milestones with tight scopes and golden tests:
- **Milestone 0:** config loader + dead money (nominal + PV) + tests
- **Milestone 1:** Phase 3 Tables 1â€“2 (ledger + schedule) + tests
- **Milestone 2:** Phase 1 cutlines + shrinkage + tests
- **Milestone 3:** Phase 1 assignment + SAV + tests (artifact regression case)
- **Milestone 4:** Phase 1 RSV/LD/CG scaffolding + tests (shape/bounds)
- **Milestone 5:** Phase 2 v0 ADPâ†’RSV calibration + quantiles + rolling backtest harness
- **Milestone 6:** Phase 3 Tables 3â€“7 using TV inputs + contract economics + instrument shortlists

**Rules**
- Do not implement multiple milestones in a single change set.
- Every milestone must include unit tests. `python -m pytest -q` must pass.
- If a rule is ambiguous, add a TODO and a failing test placeholder rather than guessing.

---

## Data Notes

### League Tycoon roster export
League Tycoon roster exports include:
- **Real Salary** (contract face value) and **Current Salary** (after PS/IR discounting)
- **Years** remaining
- Booleans for:
  - extension/tag eligibility
  - whether a player has already been extended/tagged

### Weekly projections raw input
Current raw weekly projections input is a FantasyData-style CSV. Two schema variants are supported.

Legacy raw file:
- `data/raw/fantasydata_weekly_projections_2014_2024_raw.csv`

Observed legacy raw columns:
- `Unnamed: 0` (drop as source index column)
- `PlayerID`
- `Name`
- `Team`
- `Position`
- `Opponent`
- `Year`
- `Week`
- `FantasyPointsHalfPointPpr`

Observed legacy coverage in the attached dataset:
- Years: 2014-2024
- Weeks: 1-18
- Positions present in the raw file: `QB`, `RB`, `WR`, `TE`, `K`, `FB`, `DL`, `LB`, `DB`

Current-schema raw file example:
- `data/raw/fantasydata_weekly_projections_2025_week1_raw.csv`

Observed current-schema raw columns:
- `rank`
- `id`
- `player`
- `team`
- `pos`
- `game.week`
- `opp`
- component stat columns such as `pass_yds`, `rush_yds`, `rec`, etc.
- `fpts_half_ppr`

Implementation expectation:
- Raw ingest should treat these files as weekly half-PPR projection sources.
- Modeling layers should filter player positions using `src/config/league_config.yaml` (`player_positions`) rather than hardcoding positions.
- Normalized weekly projections should map both schema variants into:
  - `season`
  - `week`
  - `player_id`
  - `player`
  - `team`
  - `position`
  - `opponent`
  - `projected_points`
  - `source`
  - `loaded_at`
- Legacy mapping:
  - `PlayerID -> player_id`
  - `Name -> player`
  - `Team -> team`
  - `Position -> position`
  - `Opponent -> opponent`
  - `Year -> season`
  - `Week -> week`
  - `FantasyPointsHalfPointPpr -> projected_points`
- Current-schema mapping:
  - `id -> player_id`
  - `player -> player`
  - `team -> team`
  - `pos -> position`
  - `opp -> opponent`
  - `game.week -> week`
  - `fpts_half_ppr -> projected_points`
- `season` must be provided as import metadata for the current schema because the export does not include a year column.
- Legacy 2014-2024 imports may contain duplicate `season/week/player_id` rows from mid-week team changes. Current master-build resolution keeps the row with the higher `projected_points`; ties keep the first row encountered.
### Instrument-adjusted contracts (validation requirement)
Instrument-adjusted contracts (extended/tagged/optioned) may break the standard +10% escalator.

Implementation rule:
- If `has_been_extended == true` or `has_been_tagged == true` (and later, optioned),
  set `needs_schedule_validation = true` unless an **observed year-by-year salary schedule** is available.

Until observed schedules exist, build a **best-effort** schedule but keep the validation flag true.

---

## Where Outputs Live

Suggested convention:
- Raw data: `data/raw/`
- Cleaned/intermediate: `data/interim/`
- Final tables/exports: `data/processed/`

Tests use tiny fixtures in `tests/fixtures/`.

---

## Naming / ID Normalization

Player names may differ across:
- League Tycoon exports
- FantasyPros ADP
- Projection/box score sources

We maintain a name mapping layer (eventually `data/external/name_map.csv`) and treat normalized `player_id` as the preferred key where possible.

---

## TODO Roadmap (High Level)

- [ ] Implement config loader (`src/utils/config.py`)
- [ ] Dead money functions (nominal + PV) and tests
- [ ] Contract ledger + schedule builder (Tables 1â€“2) and tests
- [ ] Phase 1 cutlines + shrinkage and tests
- [ ] Phase 1 assignment + SAV and artifact regression test
- [ ] Phase 2 v0 ADPâ†’RSV calibration + quantiles + rolling backtests
- [ ] Phase 3 Tables 3â€“7 populated from TV + contract economics
- [ ] Add observed contract schedule ingestion for extended/tagged/optioned players
- [ ] Add dynasty ADP ingestion and 4-horizon TV path model

