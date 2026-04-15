// Data loading and derived metric computation for ESV Fantasy Dashboard
// Reads multiple CSVs via PapaParse at app startup.

// Paths are relative to index.html (served from dashboard/src/)
const DATA_PATHS = {
  weekly:          '../data/weekly_detail.csv',
  season:          '../data/season_values.csv',
  headshots:       '../data/player_headshots.csv',
  tvInputs:        '../data/tv_inputs.csv',
  surplus:         '../data/contract_surplus.csv',
  capHealth:       '../data/team_cap_health.csv',
  ledger:          '../data/contract_ledger.csv',
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
    parseCsv(DATA_PATHS.season)
  ]).then(([weeklyRaw, seasonRaw]) => {

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
        return {
          player:       String(r.player),
          position:     String(r.position),
          season,
          esv:          +(r.esv          ?? 0) || 0,
          sav:          +(r.sav          ?? 0) || 0,
          par:          +(r.par          ?? 0) || 0,
          total_points: +(r.total_points ?? 0) || 0,
          dollar_value: +(r.dollar_value ?? 0) || 0,
          pos_rank:     posRankMap[`${season}||${r.player}`] ?? null
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
  ]).then(([headshotsRaw, tvRaw, surplusRaw, capRaw, ledgerRaw]) => {

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
        cap_today_current:        +(r.cap_today_current        ?? 0) || 0,
        dead_money_cut_now_nominal: +(r.dead_money_cut_now_nominal ?? 0) || 0,
        dead_money_cut_now_pv:    +(r.dead_money_cut_now_pv    ?? 0) || 0,
        needs_schedule_validation: r.needs_schedule_validation === true || r.needs_schedule_validation === 'True',
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

    console.log(`Headshots    : ${Object.keys(HEADSHOT_MAP).length}`);
    console.log(`TV forecasts : ${TV_DATA.length}`);
    console.log(`Surplus rows : ${SURPLUS_DATA.length}`);
    console.log(`Cap health   : ${CAP_HEALTH_DATA.length} teams`);
    console.log(`Ledger rows  : ${LEDGER_DATA.length}`);
  });

  // Return only the Phase 1 promise so the app starts as soon as historical
  // data is ready. Supplemental data populates in the background.
  return Promise.all([phase1Promise, supplementalPromise]);
}
