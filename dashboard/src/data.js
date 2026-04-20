// Data loading and derived metric computation for ESV Fantasy Dashboard
// Reads multiple CSVs via PapaParse at app startup.

// Paths are relative to index.html (served from dashboard/src/)
const DATA_PATHS = {
  weekly:              '../data/weekly_detail.csv',
  season:              '../data/season_values.csv',
  headshots:           '../data/player_headshots.csv',
  tvInputs:            '../data/tv_inputs.csv',
  surplus:             '../data/contract_surplus.csv',
  capHealth:           '../data/team_cap_health.csv',
  ledger:              '../data/contract_ledger.csv',
  faMarket:            '../data/free_agent_market.csv',
  faMarketEnv:         '../data/fa_market_environment.csv',
  redraftRankings:     '../data/redraft_rankings_master.csv',
};

// ── Phase 1 (Historical) ─────────────────────────────────────────────────────
let WEEKLY_DATA  = [];
let SEASON_DATA  = [];
let ALL_PLAYERS  = [];
let ALL_SEASONS  = [];

// ── Player bio / headshots ───────────────────────────────────────────────────
// Map: player name (string) → { headshot_url, position, birth_date,
//      height, weight, college_name, draft_year, draft_round, draft_pick, rookie_season }
let HEADSHOT_MAP = {};

// ── Phase 2 (Forecasted) ─────────────────────────────────────────────────────
let TV_DATA        = [];   // tv_inputs rows
let ALL_TV_TEAMS   = [];   // sorted unique fantasy team names from TV_DATA
let ALL_TV_PLAYERS = [];   // sorted unique player names from TV_DATA

// ── Phase 3 (League Analysis) ────────────────────────────────────────────────
let SURPLUS_DATA    = [];
let CAP_HEALTH_DATA = [];
let LEDGER_DATA     = [];
let ALL_LG_TEAMS    = [];  // sorted unique fantasy team names from SURPLUS_DATA

// ── Free Agent Market ────────────────────────────────────────────────────────
// Loaded from free_agent_market.csv (phase3 export) or computed on-the-fly in
// view-free-agent-market.js from TV_DATA + CAP_HEALTH_DATA when the CSV is absent.
let FA_MARKET_DATA = [];   // player-level market table
let FA_MARKET_ENV  = {};   // league-level cap environment (single-row CSV → object)

// ── Draft Pick Inventory ─────────────────────────────────────────────────────
// Loaded from /api/picks (Flask server) or falls back to draft_pick_inventory.csv.
// Each entry: { pick_id, year, round, slot, salary, owner }
let DRAFT_PICKS_DATA = [];   // flat inventory (picks × ownership)
let ALL_PICK_YEARS   = [];   // sorted unique draft years

// ── League Config & Team Adjustments ────────────────────────────────────────
// Loaded from Flask API endpoints. Used by Cap Health and League Settings views.
let LEAGUE_CONFIG     = {};  // editable config subset (dot-notation keys)
let TEAM_ADJUSTMENTS  = {};  // { "Team Name": { dead_money, cap_transactions, rollover } }

/**
 * Return the actual calendar year for a given TV path offset (0–3).
 * Reads season.target_season from LEAGUE_CONFIG; falls back to 2026 when
 * the server is not running and LEAGUE_CONFIG is empty.
 */
function tvYearLabel(offset) {
  const base = +(LEAGUE_CONFIG['season.target_season'] || 2026);
  return base + offset;
}

/**
 * Parse a CSV via PapaParse (download mode — works with both file:// and http://).
 * Returns a promise that resolves to the array of row objects.
 * If the request fails (404, network error) the promise resolves to [] so
 * the dashboard degrades gracefully when Phase 2/3 files are missing.
 */
function parseCsv(path) {
  return new Promise((resolve) => {
    Papa.parse(path, {
      download: true,
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
      complete: (results) => resolve(results.data),
      error: () => {
        console.warn(`Could not load ${path} — skipping.`);
        resolve([]);
      }
    });
  });
}

/**
 * Load all CSVs, compute derived metrics, and populate the exported arrays.
 * Returns a promise that resolves when Phase 1 data (required) is ready.
 * Phase 2/3 data is loaded in parallel and failures are silent.
 */
function loadData() {
  // Phase 1 is required — reject if it fails
  const phase1Promise = Promise.all([
    parseCsv(DATA_PATHS.weekly),
    parseCsv(DATA_PATHS.season),
    parseCsv(DATA_PATHS.redraftRankings)
  ]).then(([weeklyRaw, seasonRaw, redraftRaw]) => {

    // ── Weekly data ──────────────────────────────────────────────────────────
    WEEKLY_DATA = weeklyRaw
      .filter(r => r.player && r.position)
      .map(r => ({
        player:       String(r.player),
        position:     String(r.position),
        season:       +r.season,
        week:         +r.week,
        points:       +(r.points      ?? 0) || 0,
        margin:       +(r.margin      ?? 0) || 0,
        esv_week:     +(r.esv_week    ?? 0) || 0,
        wmsv:         +(r.wmsv        ?? 0) || 0,
        start_prob:   +(r.start_prob  ?? 0) || 0,
        dollar_value: +(r.dollar_value ?? 0) || 0
      }));

    // ── Pre-season positional rank map (from redraft rankings) ───────────────
    // key: "season||player" → pos_rank (integer, preseason positional rank)
    const preseasonPosRankMap = {};
    redraftRaw.forEach(r => {
      if (!r.player || !r.season || !r.pos_rank) return;
      const key = `${+r.season}||${String(r.player)}`;
      // Keep only the first occurrence (rankings are already deduplicated)
      if (!(key in preseasonPosRankMap)) {
        preseasonPosRankMap[key] = +r.pos_rank || null;
      }
    });

    // ── Season data — derived metrics ────────────────────────────────────────
    const posGroups = {};
    seasonRaw.forEach(r => {
      const key = `${r.season}||${r.position}`;
      (posGroups[key] = posGroups[key] || []).push(r);
    });
    const posRankMap = {};
    Object.values(posGroups).forEach(group => {
      group
        .slice()
        .sort((a, b) => (+(b.esv) || 0) - (+(a.esv) || 0))
        .forEach((r, i) => {
          posRankMap[`${r.season}||${r.player}`] = i + 1;
        });
    });

    SEASON_DATA = seasonRaw
      .filter(r => r.player && r.position)
      .map(r => {
        const season = +r.season;
        const key    = `${season}||${String(r.player)}`;
        return {
          player:              String(r.player),
          position:            String(r.position),
          season,
          esv:                 +(r.esv          ?? 0) || 0,
          sav:                 +(r.sav          ?? 0) || 0,
          par:                 +(r.par          ?? 0) || 0,
          total_points:        +(r.total_points ?? 0) || 0,
          dollar_value:        +(r.dollar_value ?? 0) || 0,
          pos_rank:            posRankMap[key] ?? null,
          preseason_pos_rank:  preseasonPosRankMap[key] ?? null
        };
      });

    ALL_PLAYERS = [...new Set(SEASON_DATA.map(r => r.player))].sort();
    ALL_SEASONS = [...new Set(SEASON_DATA.map(r => r.season))].sort((a, b) => a - b);

    console.log('=== ESV Fantasy Dashboard — Phase 1 Loaded ===');
    console.log(`Weekly rows  : ${WEEKLY_DATA.length.toLocaleString()}`);
    console.log(`Season rows  : ${SEASON_DATA.length.toLocaleString()}`);
    console.log(`Season range : ${ALL_SEASONS[0]}–${ALL_SEASONS[ALL_SEASONS.length - 1]}`);
    console.log(`Unique players: ${ALL_PLAYERS.length.toLocaleString()}`);
  });

  // Phase 2/3 + headshots — load in parallel, failures are silent
  const supplementalPromise = Promise.all([
    parseCsv(DATA_PATHS.headshots),
    parseCsv(DATA_PATHS.tvInputs),
    parseCsv(DATA_PATHS.surplus),
    parseCsv(DATA_PATHS.capHealth),
    parseCsv(DATA_PATHS.ledger),
    parseCsv(DATA_PATHS.faMarket),
    parseCsv(DATA_PATHS.faMarketEnv),
  ]).then(([headshotsRaw, tvRaw, surplusRaw, capRaw, ledgerRaw, faMarketRaw, faMarketEnvRaw]) => {

    // ── Headshot map ─────────────────────────────────────────────────────────
    headshotsRaw.forEach(r => {
      if (!r.player) return;
      HEADSHOT_MAP[String(r.player)] = {
        headshot_url:  r.headshot_url  || null,
        position:      r.position      || null,
        birth_date:    r.birth_date    || null,
        height:        r.height        || null,
        weight:        r.weight        || null,
        college_name:  r.college_name  || null,
        draft_year:    r.draft_year    || null,
        draft_round:   r.draft_round   || null,
        draft_pick:    r.draft_pick    || null,
        rookie_season: r.rookie_season || null,
      };
    });

    // ── Phase 2 TV inputs ────────────────────────────────────────────────────
    TV_DATA = tvRaw
      .filter(r => r.player && r.position)
      .map(r => ({
        player:     String(r.player),
        team:       String(r.team || ''),
        position:   String(r.position),
        tv_y0:      +(r.tv_y0      ?? 0) || 0,
        tv_y1:      +(r.tv_y1      ?? 0) || 0,
        tv_y2:      +(r.tv_y2      ?? 0) || 0,
        tv_y3:      +(r.tv_y3      ?? 0) || 0,
        adp:        +(r.adp        ?? 0) || 0,
        esv_hat:    +(r.esv_hat    ?? 0) || 0,
        esv_p25:    +(r.esv_p25    ?? 0) || 0,
        esv_p50:    +(r.esv_p50    ?? 0) || 0,
        esv_p75:    +(r.esv_p75    ?? 0) || 0,
        is_rostered: r.is_rostered === true || r.is_rostered === 'True',
      }));
    ALL_TV_TEAMS   = [...new Set(TV_DATA.map(r => r.team).filter(Boolean))].sort();
    ALL_TV_PLAYERS = [...new Set(TV_DATA.map(r => r.player))].sort();

    // ── Phase 3 Contract Surplus ─────────────────────────────────────────────
    SURPLUS_DATA = surplusRaw
      .filter(r => r.player)
      .map(r => ({
        player:                   String(r.player),
        team:                     String(r.team || ''),
        position:                 String(r.position || ''),
        pv_tv:                    +(r.pv_tv                    ?? 0) || 0,
        pv_cap:                   +(r.pv_cap                   ?? 0) || 0,
        surplus_value:            +(r.surplus_value            ?? 0) || 0,
        // Windowed annualized surplus fields (kept for Cap Health dashboard)
        value_1yr:                +(r.value_1yr                ?? 0) || 0,
        cap_1yr:                  +(r.cap_1yr                  ?? 0) || 0,
        surplus_1yr:              +(r.surplus_1yr              ?? 0) || 0,
        value_3yr_ann:            +(r.value_3yr_ann            ?? 0) || 0,
        cap_3yr_ann:              +(r.cap_3yr_ann              ?? 0) || 0,
        surplus_3yr_ann:          +(r.surplus_3yr_ann          ?? 0) || 0,
        value_5yr_ann:            +(r.value_5yr_ann            ?? 0) || 0,
        cap_5yr_ann:              +(r.cap_5yr_ann              ?? 0) || 0,
        surplus_5yr_ann:          +(r.surplus_5yr_ann          ?? 0) || 0,
        cap_today_current:        +(r.cap_today_current        ?? 0) || 0,
        dead_money_cut_now_nominal: +(r.dead_money_cut_now_nominal ?? 0) || 0,
        dead_money_cut_now_pv:    +(r.dead_money_cut_now_pv    ?? 0) || 0,
        needs_schedule_validation: r.needs_schedule_validation === true || r.needs_schedule_validation === 'True',
        // Contract schedule metadata
        years_remaining:          +(r.years_remaining          ?? 0) || 0,
        // Per-year value (TV), cap hit, and surplus (year indices 0–3)
        tv_y0:      +(r.tv_y0      ?? 0) || 0,
        tv_y1:      +(r.tv_y1      ?? 0) || 0,
        tv_y2:      +(r.tv_y2      ?? 0) || 0,
        tv_y3:      +(r.tv_y3      ?? 0) || 0,
        cap_y0:     +(r.cap_y0     ?? 0) || 0,
        cap_y1:     +(r.cap_y1     ?? 0) || 0,
        cap_y2:     +(r.cap_y2     ?? 0) || 0,
        cap_y3:     +(r.cap_y3     ?? 0) || 0,
        surplus_y0: +(r.surplus_y0 ?? 0) || 0,
        surplus_y1: +(r.surplus_y1 ?? 0) || 0,
        surplus_y2: +(r.surplus_y2 ?? 0) || 0,
        surplus_y3: +(r.surplus_y3 ?? 0) || 0,
        // Contract Value aggregates (over actual years_remaining)
        contract_total_value:   +(r.contract_total_value   ?? 0) || 0,
        contract_total_cap:     +(r.contract_total_cap     ?? 0) || 0,
        contract_total_surplus: +(r.contract_total_surplus ?? 0) || 0,
        contract_avg_value:     +(r.contract_avg_value     ?? 0) || 0,
        contract_avg_cap:       +(r.contract_avg_cap       ?? 0) || 0,
        contract_avg_surplus:   +(r.contract_avg_surplus   ?? 0) || 0,
      }));
    ALL_LG_TEAMS = [...new Set(SURPLUS_DATA.map(r => r.team).filter(Boolean))].sort();

    // ── Phase 3 Cap Health ───────────────────────────────────────────────────
    CAP_HEALTH_DATA = capRaw
      .filter(r => r.team)
      .map(r => ({
        team:                     String(r.team),
        current_cap_usage:        +(r.current_cap_usage        ?? 0) || 0,
        real_cap_y0:              +(r.real_cap_y0              ?? 0) || 0,
        real_cap_y1:              +(r.real_cap_y1              ?? 0) || 0,
        real_cap_y2:              +(r.real_cap_y2              ?? 0) || 0,
        real_cap_y3:              +(r.real_cap_y3              ?? 0) || 0,
        total_pv_cap:             +(r.total_pv_cap             ?? 0) || 0,
        total_pv_tv:              +(r.total_pv_tv              ?? 0) || 0,
        total_surplus:            +(r.total_surplus            ?? 0) || 0,
        // Windowed annualized team totals
        total_value_1yr:          +(r.total_value_1yr          ?? 0) || 0,
        total_cap_1yr:            +(r.total_cap_1yr            ?? 0) || 0,
        total_surplus_1yr:        +(r.total_surplus_1yr        ?? 0) || 0,
        total_value_3yr_ann:      +(r.total_value_3yr_ann      ?? 0) || 0,
        total_cap_3yr_ann:        +(r.total_cap_3yr_ann        ?? 0) || 0,
        total_surplus_3yr_ann:    +(r.total_surplus_3yr_ann    ?? 0) || 0,
        total_value_5yr_ann:      +(r.total_value_5yr_ann      ?? 0) || 0,
        total_cap_5yr_ann:        +(r.total_cap_5yr_ann        ?? 0) || 0,
        total_surplus_5yr_ann:    +(r.total_surplus_5yr_ann    ?? 0) || 0,
        dead_money_cut_now_nominal: +(r.dead_money_cut_now_nominal ?? 0) || 0,
      }));

    // ── Phase 3 Contract Ledger ──────────────────────────────────────────────
    LEDGER_DATA = ledgerRaw
      .filter(r => r.player)
      .map(r => ({
        player:              String(r.player),
        team:                String(r.team || ''),
        position:            String(r.position || ''),
        current_salary:      +(r.current_salary   ?? 0) || 0,
        real_salary:         +(r.real_salary      ?? 0) || 0,
        extension_salary:    +(r.extension_salary ?? 0) || 0,
        years_remaining:     +(r.years_remaining  ?? 0) || 0,
        contract_type_bucket: String(r.contract_type_bucket || ''),
        extension_eligible:  r.extension_eligible === true || r.extension_eligible === 'True',
        tag_eligible:        r.tag_eligible === true || r.tag_eligible === 'True',
        needs_schedule_validation: r.needs_schedule_validation === true || r.needs_schedule_validation === 'True',
      }));

    // ── Free Agent Market ─────────────────────────────────────────────────────
    FA_MARKET_DATA = faMarketRaw
      .filter(r => r.player && r.position)
      .map(r => ({
        player:                String(r.player),
        position:              String(r.position),
        team:                  String(r.team || ''),
        adp:                   +(r.adp          ?? 0) || 0,
        is_rostered:           r.is_rostered === true || r.is_rostered === 'True',
        esv_p25:               +(r.esv_p25      ?? 0) || 0,
        esv_p50:               +(r.esv_p50      ?? 0) || 0,
        esv_p75:               +(r.esv_p75      ?? 0) || 0,
        projected_value:       +(r.projected_value       ?? 0) || 0,
        market_adjusted_value: +(r.market_adjusted_value ?? 0) || 0,
        market_premium_pct:    +(r.market_premium_pct    ?? 0) || 0,
      }));

    if (faMarketEnvRaw.length > 0) {
      const envRow = faMarketEnvRaw[0];
      FA_MARKET_ENV = {
        total_cap_available:    +(envRow.total_cap_available    ?? null),
        total_rollover:         +(envRow.total_rollover         ?? null),
        effective_cap_available:+(envRow.effective_cap_available?? null),
        total_fa_value:         +(envRow.total_fa_value         ?? null),
        cap_to_value_ratio:     +(envRow.cap_to_value_ratio     ?? null),
        market_multiplier:      +(envRow.market_multiplier      ?? null),
        inflation_pct:          +(envRow.inflation_pct          ?? null),
        alpha:                  +(envRow.alpha                  ?? null),
      };
    }

    console.log(`Headshots    : ${Object.keys(HEADSHOT_MAP).length}`);
    console.log(`TV forecasts : ${TV_DATA.length}`);
    console.log(`Surplus rows : ${SURPLUS_DATA.length}`);
    console.log(`Cap health   : ${CAP_HEALTH_DATA.length} teams`);
    console.log(`Ledger rows  : ${LEDGER_DATA.length}`);
    console.log(`FA market    : ${FA_MARKET_DATA.length} players`);
  });

  // Draft picks — loaded from the Flask API if available, else from static CSV.
  const picksPromise = fetch('/api/picks')
    .then(r => {
      if (!r.ok) throw new Error(`/api/picks returned ${r.status}`);
      return r.json();
    })
    .then(({ picks, ownership }) => {
      // ownership values are now {original_team, owner, slot} records.
      DRAFT_PICKS_DATA = picks.map(p => ({
        ...p,
        owner: (ownership[p.pick_id] || {}).owner || p.original_team || null,
      }));
      ALL_PICK_YEARS = [...new Set(DRAFT_PICKS_DATA.map(p => p.year))].sort((a, b) => a - b);
      console.log(`Draft picks  : ${DRAFT_PICKS_DATA.length} picks across ${ALL_PICK_YEARS.length} years`);
    })
    .catch(() => {
      // Server not running — try static CSV fallback.
      return parseCsv('../data/draft_pick_inventory.csv').then(rows => {
        DRAFT_PICKS_DATA = rows.map(r => ({
          pick_id: String(r.pick_id || ''),
          year:    +r.year  || 0,
          round:   +r.round || 0,
          slot:    +r.slot  || 0,
          salary:  r.salary !== '' && r.salary != null ? +r.salary : null,
          owner:   r.owner  || null,
        })).filter(r => r.pick_id);
        ALL_PICK_YEARS = [...new Set(DRAFT_PICKS_DATA.map(p => p.year))].sort((a, b) => a - b);
        console.log(`Draft picks (CSV): ${DRAFT_PICKS_DATA.length} rows`);
      });
    });

  // League config & team adjustments — loaded from Flask API, silent on failure.
  const configPromise = fetch('/api/config')
    .then(r => {
      if (!r.ok) throw new Error(`/api/config returned ${r.status}`);
      return r.json();
    })
    .then(({ config }) => {
      Object.assign(LEAGUE_CONFIG, config || {});
      console.log(`League config: loaded ${Object.keys(LEAGUE_CONFIG).length} fields`);
    })
    .catch(() => { /* Server not running — LEAGUE_CONFIG stays empty */ });

  const adjustmentsPromise = fetch('/api/team-adjustments')
    .then(r => {
      if (!r.ok) throw new Error(`/api/team-adjustments returned ${r.status}`);
      return r.json();
    })
    .then(({ adjustments }) => {
      Object.assign(TEAM_ADJUSTMENTS, adjustments || {});
      console.log(`Team adjustments: ${Object.keys(TEAM_ADJUSTMENTS).length} teams`);
    })
    .catch(() => { /* Server not running — TEAM_ADJUSTMENTS stays empty */ });

  // Return only the Phase 1 promise so the app starts as soon as historical
  // data is ready. Supplemental data populates in the background.
  return Promise.all([phase1Promise, supplementalPromise, picksPromise, configPromise, adjustmentsPromise]);
}
